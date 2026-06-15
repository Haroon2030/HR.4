"""API وكيل البصمة — استقبال من شبكة الفرع."""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.attendance.api.serializers import AgentIngestSerializer
from apps.attendance.authentication import AgentAPIKeyAuthentication, AttendanceAgentPrincipal
from apps.attendance.models import AttendanceIngestLog, BiometricDevice
from apps.attendance.services.agent_ingest import ingest_agent_payload
from apps.attendance.services.ingest_audit import log_ingest_attempt
from apps.attendance.services.punch_sync import (
    INCREMENTAL_BUFFER_SECONDS,
    get_device_punch_watermark,
)
from apps.attendance.services.agent_pull_queue import (
    acknowledge_pull_request,
    acknowledge_pull_request_after_ingest,
    list_pending_pull_requests,
)
from apps.attendance.middleware import ingest_body_unreadable
from apps.attendance.services.ingest_signature import (
    extract_provided_signature,
    get_ingest_body,
    signature_required,
    verify_ingest_signature,
)

logger = logging.getLogger(__name__)


class AgentRateThrottle(SimpleRateThrottle):
    scope = 'attendance_agent'

    def get_cache_key(self, request, view):
        principal = getattr(request, 'user', None)
        ident = 'agent'
        if isinstance(principal, AttendanceAgentPrincipal) and principal.device is not None:
            ident = f'device-{principal.device.pk}'
        return self.cache_format % {'scope': self.scope, 'ident': ident}


def _deny_global_key_metadata(request) -> None:
    """في الإنتاج: المفتاح العام لا يستعلم قائمة الأجهزة/طلبات السحب."""
    from django.conf import settings

    if settings.DEBUG or getattr(settings, 'AGENT_GLOBAL_KEY_LIST_DEVICES', False):
        return
    principal = request.user
    if isinstance(principal, AttendanceAgentPrincipal) and principal.is_global_key:
        raise PermissionDenied(
            'المفتاح العام لا يمكنه هذا الإجراء في الإنتاج. '
            'استخدم مفتاحاً لكل جهاز (AGENT_GLOBAL_KEY_LIST_DEVICES=true للاستثناء).'
        )


def _deny_global_key_ingest(request) -> None:
    """في الإنتاج: المفتاح العام لا يُدخل بصمات لأي جهاز."""
    from django.conf import settings

    if settings.DEBUG or getattr(settings, 'AGENT_GLOBAL_KEY_ALLOW_INGEST', False):
        return
    principal = request.user
    if isinstance(principal, AttendanceAgentPrincipal) and principal.is_global_key:
        raise PermissionDenied(
            'المفتاح العام لا يمكنه إدخال البصمات في الإنتاج. '
            'استخدم مفتاحاً لكل جهاز.'
        )


def _assert_device_access(request, device_id: int) -> BiometricDevice:
    """يمنع مفتاح جهاز من العمل على جهاز آخر."""
    principal = request.user
    if not isinstance(principal, AttendanceAgentPrincipal):
        raise PermissionDenied('مصادقة وكيل غير صالحة.')
    if principal.is_global_key:
        return get_object_or_404(
            BiometricDevice,
            pk=device_id,
            is_deleted=False,
            is_active=True,
        )
    if principal.device is None or principal.device.pk != device_id:
        raise PermissionDenied('المفتاح غير مصرح لهذا الجهاز.')
    return principal.device


class AgentDeviceListView(APIView):
    """قائمة أجهزة نشطة للوكيل (للإعداد)."""

    authentication_classes = [AgentAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentRateThrottle]

    def get(self, request):
        _deny_global_key_metadata(request)
        principal = request.user
        devices = BiometricDevice.objects.filter(
            is_deleted=False, is_active=True,
        ).order_by('name')
        if (
            isinstance(principal, AttendanceAgentPrincipal)
            and principal.device is not None
            and not principal.is_global_key
        ):
            devices = devices.filter(pk=principal.device.pk)
        data = [
            {
                'id': d.pk,
                'name': d.name,
                'ip_address': d.ip_address,
                'port': d.port,
                'comm_key': int(d.comm_key or 0),
                'branch_id': d.branch_id,
                'branch_name': d.branch.name if d.branch_id else '',
            }
            for d in devices
        ]
        return Response({'success': True, 'data': data})


class AgentPullRequestsView(APIView):
    """طلبات سحب من لوحة HR — الوكيل في الفرع ينفّذها."""

    authentication_classes = [AgentAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentRateThrottle]

    def get(self, request):
        _deny_global_key_metadata(request)
        principal = request.user
        device_id = None
        if (
            isinstance(principal, AttendanceAgentPrincipal)
            and principal.device is not None
            and not principal.is_global_key
        ):
            device_id = principal.device.pk
        return Response({
            'success': True,
            'data': list_pending_pull_requests(device_id=device_id),
        })

    def post(self, request):
        device_id = request.data.get('device_id')
        if device_id is None:
            return Response(
                {'success': False, 'message': 'device_id مطلوب'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _assert_device_access(request, int(device_id))
        acknowledge_pull_request(int(device_id))
        return Response({'success': True, 'message': 'تم إغلاق طلب السحب'})


class AgentSyncStateView(APIView):
    """حالة السحب التزايدي — آخر بصمة محفوظة للجهاز (للوكيل قبل الرفع)."""

    authentication_classes = [AgentAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentRateThrottle]

    def get(self, request):
        device_id = request.query_params.get('device_id')
        if device_id is None:
            return Response(
                {'success': False, 'message': 'device_id مطلوب'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        device = _assert_device_access(request, int(device_id))
        watermark = get_device_punch_watermark(device.pk)
        return Response({
            'success': True,
            'data': {
                'device_id': device.pk,
                'last_punch_at': watermark.isoformat() if watermark else None,
                'incremental_buffer_seconds': INCREMENTAL_BUFFER_SECONDS,
            },
        })


class AgentIngestView(APIView):
    """POST دفعة بصمات من الوكيل المحلي."""

    authentication_classes = [AgentAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentRateThrottle]

    def post(self, request):
        _deny_global_key_ingest(request)
        if ingest_body_unreadable(request):
            msg = 'انقطع الاتصال قبل اكتمال استلام البيانات — أعد المحاولة.'
            logger.warning('Agent ingest rejected: incomplete request body (client disconnected)')
            log_ingest_attempt(
                request=request,
                device=getattr(request.user, 'device', None),
                status=AttendanceIngestLog.Status.REJECTED_PAYLOAD,
                signature_valid=None,
                message=msg,
            )
            return Response(
                {'success': False, 'message': msg, 'code': 'incomplete_body'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        principal = request.user
        raw_key = (
            principal.api_key_presented
            if isinstance(principal, AttendanceAgentPrincipal)
            else ''
        )
        body = get_ingest_body(request)
        provided_sig = extract_provided_signature(request)
        require_sig = signature_required()

        device_hint = getattr(getattr(principal, 'device', None), 'pk', None)
        if require_sig and not provided_sig:
            msg = 'توقيع الطلب مطلوب (X-Attendance-Signature).'
            logger.warning(
                'Agent ingest rejected: missing signature (device_key=%s body_len=%s)',
                device_hint,
                len(body),
            )
            log_ingest_attempt(
                request=request,
                device=getattr(principal, 'device', None),
                status=AttendanceIngestLog.Status.REJECTED_SIGNATURE,
                signature_valid=False,
                message=msg,
            )
            return Response(
                {'success': False, 'message': msg, 'code': 'missing_signature'},
                status=status.HTTP_403_FORBIDDEN,
            )

        sig_valid: bool | None = None
        if provided_sig:
            sig_valid = verify_ingest_signature(raw_key, body, provided_sig)
            if not sig_valid:
                msg = 'توقيع الطلب غير صالح.'
                logger.warning(
                    'Agent ingest rejected: invalid signature (device_key=%s body_len=%s)',
                    device_hint,
                    len(body),
                )
                log_ingest_attempt(
                    request=request,
                    device=getattr(principal, 'device', None),
                    status=AttendanceIngestLog.Status.REJECTED_SIGNATURE,
                    signature_valid=False,
                    message=msg,
                )
                return Response(
                    {'success': False, 'message': msg, 'code': 'invalid_signature'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif require_sig:
            sig_valid = False

        serializer = AgentIngestSerializer(data=request.data)
        if not serializer.is_valid():
            log_ingest_attempt(
                request=request,
                device=getattr(principal, 'device', None),
                status=AttendanceIngestLog.Status.REJECTED_PAYLOAD,
                signature_valid=sig_valid,
                message=str(serializer.errors),
            )
            serializer.is_valid(raise_exception=True)

        payload = serializer.validated_data
        device = _assert_device_access(request, int(payload['device_id']))

        punches_payload = [dict(p) for p in payload['punches']]
        users_payload = [dict(u) for u in payload['users']] if payload.get('users') else None

        try:
            result = ingest_agent_payload(
                device,
                punches=punches_payload,
                users=users_payload,
                incremental=payload.get('incremental', True),
            )
        except ValueError as exc:
            log_ingest_attempt(
                request=request,
                device=device,
                agent_id=(payload.get('agent_id') or '').strip(),
                status=AttendanceIngestLog.Status.REJECTED_PAYLOAD,
                signature_valid=sig_valid,
                punches_received=len(punches_payload),
                message=str(exc),
            )
            return Response(
                {'success': False, 'message': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agent_id = (payload.get('agent_id') or '').strip()
        msg = (
            f'استلم {result.punches_received} — جديد {result.imported} — '
            f'مكرر {result.skipped_duplicate}'
        )
        if result.skipped_time_filter:
            msg += f' — قديم {result.skipped_time_filter}'
        if result.skipped_out_of_bounds:
            msg += f' — خارج النافذة {result.skipped_out_of_bounds}'

        pull_acknowledged = acknowledge_pull_request_after_ingest(device.pk)

        log_ingest_attempt(
            request=request,
            device=device,
            agent_id=agent_id,
            status=AttendanceIngestLog.Status.SUCCESS,
            signature_valid=sig_valid,
            punches_received=result.punches_received,
            imported=result.imported,
            skipped_duplicate=result.skipped_duplicate,
            skipped_time_filter=result.skipped_time_filter,
            users_updated=result.users_updated,
            message=msg,
        )

        return Response({
            'success': True,
            'message': msg,
            'data': {
                'agent_id': agent_id,
                'device_id': device.pk,
                'imported': result.imported,
                'skipped_duplicate': result.skipped_duplicate,
                'skipped_time_filter': result.skipped_time_filter,
                'skipped_out_of_bounds': result.skipped_out_of_bounds,
                'punches_received': result.punches_received,
                'users_updated': result.users_updated,
                'batch': result.batch,
                'pull_acknowledged': pull_acknowledged,
                'last_punch_at': (
                    result.last_punch_at.isoformat() if result.last_punch_at else None
                ),
            },
        })

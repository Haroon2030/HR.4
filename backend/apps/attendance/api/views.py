"""API وكيل البصمة — استقبال من شبكة الفرع."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.attendance.api.serializers import AgentIngestSerializer
from apps.attendance.authentication import AgentAPIKeyAuthentication
from apps.attendance.models import BiometricDevice
from apps.attendance.services.agent_ingest import ingest_agent_payload
from apps.attendance.services.agent_pull_queue import (
    acknowledge_pull_request,
    list_pending_pull_requests,
)


class AgentRateThrottle(SimpleRateThrottle):
    scope = 'attendance_agent'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': 'agent'}


class AgentDeviceListView(APIView):
    """قائمة أجهزة نشطة للوكيل (للإعداد)."""

    authentication_classes = [AgentAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentRateThrottle]

    def get(self, request):
        devices = BiometricDevice.objects.filter(
            is_deleted=False, is_active=True,
        ).order_by('name')
        data = [
            {
                'id': d.pk,
                'name': d.name,
                'ip_address': d.ip_address,
                'port': d.port,
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
        return Response({'success': True, 'data': list_pending_pull_requests()})

    def post(self, request):
        device_id = request.data.get('device_id')
        if device_id is None:
            return Response(
                {'success': False, 'message': 'device_id مطلوب'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        acknowledge_pull_request(int(device_id))
        return Response({'success': True, 'message': 'تم إغلاق طلب السحب'})


class AgentIngestView(APIView):
    """POST دفعة بصمات من الوكيل المحلي."""

    authentication_classes = [AgentAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentRateThrottle]

    def post(self, request):
        serializer = AgentIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        device = get_object_or_404(
            BiometricDevice,
            pk=payload['device_id'],
            is_deleted=False,
        )

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

        return Response({
            'success': True,
            'message': msg,
            'data': {
                'agent_id': agent_id,
                'device_id': device.pk,
                'imported': result.imported,
                'skipped_duplicate': result.skipped_duplicate,
                'skipped_time_filter': result.skipped_time_filter,
                'punches_received': result.punches_received,
                'users_updated': result.users_updated,
                'batch': result.batch,
            },
        })

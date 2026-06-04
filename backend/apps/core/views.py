"""
النظام الأساسي - API Views
"""
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .api_permissions import ActionPermissionMixin, has_app_permission
from .models import Role, UserProfile, Branch, Company, Permission
from .services.access_control import (
    assignable_roles_queryset,
    can_administer_user,
    can_assign_role,
    filter_branches_queryset,
    filter_users_queryset,
    validate_user_admin_changes,
)
from .serializers import (
    RoleSerializer,
    RoleListSerializer,
    UserSerializer,
    UserProfileSerializer,
    BranchSerializer,
    BranchListSerializer,
    CompanySerializer,
)

User = get_user_model()


class CompanyViewSet(ActionPermissionMixin, viewsets.ModelViewSet):
    """ViewSet للشركات"""
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_deleted']
    search_fields = ['name', 'tax_number', 'commercial_record']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    permission_map = {
        'list': 'users.view',
        'retrieve': 'users.view',
        'create': 'users.edit',
        'update': 'users.edit',
        'partial_update': 'users.edit',
        'destroy': 'users.delete',
    }


class BranchViewSet(ActionPermissionMixin, viewsets.ModelViewSet):
    """ViewSet للفروع"""
    queryset = Branch.objects.select_related('company', 'manager').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'company']
    search_fields = ['name', 'code', 'address']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']
    permission_map = {
        'list': 'branches.view',
        'retrieve': 'branches.view',
        'create': 'branches.add',
        'update': 'branches.edit',
        'partial_update': 'branches.edit',
        'destroy': 'branches.delete',
        'employees': 'branches.view',
    }

    def get_serializer_class(self):
        if self.action == 'list':
            return BranchListSerializer
        return BranchSerializer

    def get_queryset(self):
        from django.db.models import Count, Q
        from apps.employees.models import Employee

        # أسماء مختلفة عن @property على النموذج — تجنّب "has no setter" عند التسلسل
        queryset = super().get_queryset().annotate(
            _api_employees_count=Count(
                'employee_records',
                filter=Q(employee_records__is_deleted=False),
                distinct=True,
            ),
            _api_active_employees_count=Count(
                'employee_records',
                filter=Q(
                    employee_records__is_deleted=False,
                    employee_records__status__in=[
                        Employee.Status.ACTIVE,
                        Employee.Status.LEAVE,
                    ],
                ),
                distinct=True,
            ),
        )
        return filter_branches_queryset(self.request.user, queryset)

    @action(detail=True, methods=['get'])
    def employees(self, request, pk=None):
        """الحصول على موظفي الفرع"""
        branch = self.get_object()
        employees = branch.employees.select_related('user', 'role').all()
        return Response(UserProfileSerializer(employees, many=True).data)


class RoleViewSet(ActionPermissionMixin, viewsets.ModelViewSet):
    """ViewSet للأدوار"""
    queryset = Role.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    permission_map = {
        'list': 'users.view',
        'retrieve': 'users.view',
        'create': 'users.add',
        'update': 'users.edit',
        'partial_update': 'users.edit',
        'destroy': 'users.delete',
        'assign_permissions': 'users.edit',
        'add_permission': 'users.edit',
        'remove_permission': 'users.edit',
    }

    def get_serializer_class(self):
        if self.action == 'list':
            return RoleListSerializer
        return RoleSerializer

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated, has_app_permission('users.edit')],
    )
    def assign_permissions(self, request, pk=None):
        """تعيين صلاحيات للدور"""
        role = self.get_object()
        permission_ids = request.data.get('permission_ids', [])
        permissions = Permission.objects.filter(id__in=permission_ids)
        role.permissions.set(permissions)
        return Response(RoleSerializer(role).data)

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated, has_app_permission('users.edit')],
    )
    def add_permission(self, request, pk=None):
        """إضافة صلاحية للدور"""
        role = self.get_object()
        permission_id = request.data.get('permission_id')
        try:
            permission = Permission.objects.get(id=permission_id)
            role.permissions.add(permission)
            return Response(RoleSerializer(role).data)
        except Permission.DoesNotExist:
            return Response(
                {'error': 'الصلاحية غير موجودة'},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated, has_app_permission('users.edit')],
    )
    def remove_permission(self, request, pk=None):
        """إزالة صلاحية من الدور"""
        role = self.get_object()
        permission_id = request.data.get('permission_id')
        try:
            permission = Permission.objects.get(id=permission_id)
            role.permissions.remove(permission)
            return Response(RoleSerializer(role).data)
        except Permission.DoesNotExist:
            return Response(
                {'error': 'الصلاحية غير موجودة'},
                status=status.HTTP_404_NOT_FOUND,
            )


class UserViewSet(ActionPermissionMixin, viewsets.ModelViewSet):
    """ViewSet للمستخدمين"""
    queryset = User.objects.select_related('profile', 'profile__role').all()
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined', 'last_login']
    ordering = ['username']
    permission_map = {
        'list': 'users.view',
        'retrieve': 'users.view',
        'create': 'users.add',
        'update': 'users.edit',
        'partial_update': 'users.edit',
        'destroy': 'users.delete',
        'roles': 'users.view',
        'assign_role': 'users.edit',
    }

    def get_queryset(self):
        return filter_users_queryset(self.request.user, super().get_queryset())

    @action(detail=False, methods=['get'])
    def roles(self, request):
        """الحصول على قائمة الأدوار المتاحة"""
        roles = assignable_roles_queryset(request.user)
        return Response(RoleListSerializer(roles, many=True).data)

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated, has_app_permission('users.edit')],
    )
    def assign_role(self, request, pk=None):
        """تعيين دور للمستخدم"""
        user = self.get_object()
        role_id = request.data.get('role_id')
        profile, _ = UserProfile.objects.get_or_create(user=user)

        new_role = None
        if role_id:
            try:
                new_role = Role.objects.get(id=role_id)
            except Role.DoesNotExist:
                return Response(
                    {'error': 'الدور غير موجود'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        err = validate_user_admin_changes(
            request.user,
            user,
            new_role=new_role,
        )
        if err:
            return Response({'error': err}, status=status.HTTP_403_FORBIDDEN)

        if new_role and not can_assign_role(request.user, new_role):
            return Response(
                {'error': 'لا يمكنك تعيين هذا الدور.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not can_administer_user(request.user, user) and request.user.pk != user.pk:
            return Response(
                {'error': 'لا تملك صلاحية إدارة هذا المستخدم.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        profile.role = new_role
        profile.save()
        return Response(UserSerializer(user, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """الحصول على معلومات المستخدم الحالي"""
    user = request.user

    profile_data = {}
    if hasattr(user, 'profile'):
        profile = user.profile
        profile_data = {
            'role': profile.role.id if profile.role else None,
            'role_name': profile.role.name if profile.role else None,
            'role_type': profile.role.role_type if profile.role else None,
        }

    from apps.core.decorators import get_user_permissions

    payload = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name() or user.username,
        'is_staff': user.is_staff,
        'permissions': sorted(get_user_permissions(user)),
        **profile_data,
    }
    if user.is_superuser:
        payload['is_superuser'] = True

    return Response(payload)

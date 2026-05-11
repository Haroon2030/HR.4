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

from .models import Role, UserProfile, Branch, Company, Permission
from .serializers import (
    RoleSerializer, 
    RoleListSerializer,
    UserSerializer,
    UserProfileSerializer,
    BranchSerializer,
    BranchListSerializer,
    CompanySerializer
)

User = get_user_model()


class CompanyViewSet(viewsets.ModelViewSet):
    """ViewSet للشركات"""
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'tax_number', 'commercial_record']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class BranchViewSet(viewsets.ModelViewSet):
    """ViewSet للفروع"""
    queryset = Branch.objects.select_related('company', 'manager').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'company']
    search_fields = ['name', 'code', 'address']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return BranchListSerializer
        return BranchSerializer
    
    def get_queryset(self):
        """
        فلترة الفروع بناءً على صلاحيات المستخدم
        """
        queryset = super().get_queryset()
        user = self.request.user
        
        # التحقق من وجود profile
        if not hasattr(user, 'profile') or not user.profile.role:
            return queryset.none()
        
        # الأدمن ومدير الموارد البشرية يرون كل الفروع
        if user.profile.role.role_type in ['admin', 'hr_manager']:
            return queryset
        
        # باقي المستخدمين يرون الفروع التي يمكنهم الوصول إليها
        accessible_branches = user.profile.get_accessible_branches()
        return queryset.filter(id__in=accessible_branches.values_list('id', flat=True))
    
    @action(detail=True, methods=['get'])
    def employees(self, request, pk=None):
        """الحصول على موظفي الفرع"""
        branch = self.get_object()
        employees = branch.employees.select_related('user', 'role').all()
        return Response(UserProfileSerializer(employees, many=True).data)


class RoleViewSet(viewsets.ModelViewSet):
    """ViewSet للأدوار"""
    queryset = Role.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return RoleListSerializer
        return RoleSerializer
    
    @action(detail=True, methods=['post'])
    def assign_permissions(self, request, pk=None):
        """تعيين صلاحيات للدور"""
        role = self.get_object()
        permission_ids = request.data.get('permission_ids', [])
        permissions = Permission.objects.filter(id__in=permission_ids)
        role.permissions.set(permissions)
        return Response(RoleSerializer(role).data)
    
    @action(detail=True, methods=['post'])
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
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
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
                status=status.HTTP_404_NOT_FOUND
            )


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet للمستخدمين"""
    queryset = User.objects.select_related('profile', 'profile__role').all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined', 'last_login']
    ordering = ['username']
    
    @action(detail=False, methods=['get'])
    def roles(self, request):
        """الحصول على قائمة الأدوار المتاحة"""
        roles = Role.objects.filter(is_active=True)
        return Response(RoleListSerializer(roles, many=True).data)
    
    @action(detail=True, methods=['post'])
    def assign_role(self, request, pk=None):
        """تعيين دور للمستخدم"""
        user = self.get_object()
        role_id = request.data.get('role_id')
        profile, _ = UserProfile.objects.get_or_create(user=user)
        
        if role_id:
            try:
                role = Role.objects.get(id=role_id)
                profile.role = role
            except Role.DoesNotExist:
                return Response(
                    {'error': 'الدور غير موجود'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            profile.role = None
        
        profile.save()
        return Response(UserSerializer(user).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """الحصول على معلومات المستخدم الحالي"""
    user = request.user
    
    # Get profile info
    profile_data = {}
    if hasattr(user, 'profile'):
        profile = user.profile
        profile_data = {
            'role': profile.role.id if profile.role else None,
            'role_name': profile.role.name if profile.role else None,
            'role_type': profile.role.role_type if profile.role else None,
        }
    
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name() or user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'permissions': list(user.get_all_permissions()),
        **profile_data
    })

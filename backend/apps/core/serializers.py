"""
النظام الأساسي - Serializers
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Role, UserProfile, Branch, Company

User = get_user_model()


class CompanySerializer(serializers.ModelSerializer):
    """Serializer للشركات"""
    branches_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'tax_number', 'commercial_record', 'logo',
            'contact_email', 'contact_phone', 'address',
            'branches_count', 'is_deleted', 'deleted_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_branches_count(self, obj):
        return obj.branches.count()


class BranchSerializer(serializers.ModelSerializer):
    """Serializer للفروع"""
    company_name = serializers.CharField(source='company.name', read_only=True)
    manager_name = serializers.SerializerMethodField()
    employees_count = serializers.ReadOnlyField()
    active_employees_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'code', 'company', 'company_name',
            'manager', 'manager_name', 'address', 'phone', 'email',
            'employees_count', 'active_employees_count',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_manager_name(self, obj):
        if obj.manager:
            return obj.manager.get_full_name() or obj.manager.username
        return None


class BranchListSerializer(serializers.ModelSerializer):
    """Serializer مختصر للفروع (للقوائم المنسدلة)"""
    class Meta:
        model = Branch
        fields = ['id', 'name', 'code']


class RoleSerializer(serializers.ModelSerializer):
    """Serializer للأدوار"""
    users_count = serializers.SerializerMethodField()
    role_type_display = serializers.CharField(source='get_role_type_display', read_only=True)
    
    class Meta:
        model = Role
        fields = [
            'id', 'name', 'role_type', 'role_type_display', 'description', 
            'users_count', 'is_active', 'is_system_role',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_users_count(self, obj):
        return obj.users.count()


class RoleListSerializer(serializers.ModelSerializer):
    """Serializer مختصر للأدوار"""
    permissions_count = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    role_type_display = serializers.CharField(source='get_role_type_display', read_only=True)
    
    class Meta:
        model = Role
        fields = [
            'id', 'name', 'role_type', 'role_type_display', 'description', 
            'permissions_count', 'users_count', 
            'is_active', 'is_system_role', 'created_at'
        ]
    
    def get_permissions_count(self, obj):
        return obj.permissions.count()
    
    def get_users_count(self, obj):
        return obj.users.count()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer لملف المستخدم"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    full_name = serializers.SerializerMethodField()
    role_name = serializers.CharField(source='role.name', read_only=True)
    role_type = serializers.CharField(source='role.role_type', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    assigned_branches_list = BranchListSerializer(source='assigned_branches', many=True, read_only=True)
    accessible_branches = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'username', 'email', 
            'first_name', 'last_name', 'full_name',
            'role', 'role_name', 'role_type', 'permissions',
            'branch', 'branch_name', 'assigned_branches', 'assigned_branches_list',
            'accessible_branches',
            'phone', 'department', 'position', 'avatar'
        ]
    
    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    
    def get_permissions(self, obj):
        return obj.get_permissions()
    
    def get_accessible_branches(self, obj):
        """الفروع التي يمكن للمستخدم الوصول إليها"""
        branches = obj.get_accessible_branches()
        return BranchListSerializer(branches, many=True).data


class UserSerializer(serializers.ModelSerializer):
    """Serializer للمستخدمين"""
    profile = UserProfileSerializer(read_only=True)
    role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    password = serializers.CharField(write_only=True, required=False)
    
    # Read-only fields from profile
    role_name = serializers.CharField(source='profile.role.name', read_only=True)
    role_type = serializers.CharField(source='profile.role.role_type', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_login',
            'profile', 'role', 'password',
            'role_name', 'role_type'
        ]
        read_only_fields = ['date_joined', 'last_login', 'is_staff', 'is_superuser']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.user.is_superuser:
            self.fields['is_staff'].read_only = False
            self.fields['is_superuser'].read_only = False

    def _strip_privileged_fields(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_superuser:
            validated_data.pop('is_staff', None)
            validated_data.pop('is_superuser', None)
        return validated_data

    def create(self, validated_data):
        validated_data = self._strip_privileged_fields(validated_data)
        role = validated_data.pop('role', None)
        password = validated_data.pop('password', None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        # إنشاء ملف المستخدم
        UserProfile.objects.create(user=user, role=role)
        return user
    
    def update(self, instance, validated_data):
        validated_data = self._strip_privileged_fields(validated_data)
        role = validated_data.pop('role', None)
        password = validated_data.pop('password', None)

        request = self.context.get('request')
        if request and not request.user.is_superuser and instance.is_superuser:
            raise serializers.ValidationError(
                {'detail': 'لا يمكن تعديل حساب مدير النظام بدون صلاحيات مدير النظام.'}
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        
        # تحديث الدور في ملف المستخدم
        profile, _ = UserProfile.objects.get_or_create(user=instance)
        if role is not None:
            profile.role = role
        profile.save()
        
        return instance

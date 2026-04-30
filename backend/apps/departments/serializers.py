"""
Departments Serializers
المسلسلات الخاصة بالأقسام
"""
from rest_framework import serializers
from .models import Department


class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department"""
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    cost_center_name = serializers.CharField(source='cost_center.name', read_only=True)
    manager_name = serializers.SerializerMethodField()
    employees_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Department
        fields = [
            'id', 'code', 'name', 'branch', 'branch_name',
            'cost_center', 'cost_center_name', 
            'manager', 'manager_name',
            'description', 'is_active',
            'employees_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_manager_name(self, obj):
        if obj.manager and obj.manager.user:
            return obj.manager.user.get_full_name() or obj.manager.user.username
        return None


class DepartmentListSerializer(serializers.ModelSerializer):
    """Minimal serializer for dropdowns"""
    
    class Meta:
        model = Department
        fields = ['id', 'code', 'name']


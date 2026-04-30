"""
Cost Centers Serializers
المسلسلات الخاصة بمراكز التكلفة
"""
from rest_framework import serializers
from .models import CostCenter


class CostCenterSerializer(serializers.ModelSerializer):
    """Serializer for CostCenter"""
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    departments_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = CostCenter
        fields = [
            'id', 'code', 'name', 'branch', 'branch_name',
            'description', 'budget', 'is_active',
            'departments_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class CostCenterListSerializer(serializers.ModelSerializer):
    """Minimal serializer for dropdowns"""
    
    class Meta:
        model = CostCenter
        fields = ['id', 'code', 'name']

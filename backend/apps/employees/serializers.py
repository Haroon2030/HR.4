"""Serializers لموظفي HR — واجهة API."""
from rest_framework import serializers

from apps.employees.models import Employee


class BranchEmployeeListSerializer(serializers.ModelSerializer):
    """قائمة مختصرة لموظفي فرع — API فقط."""

    department_name = serializers.CharField(source='department.name', read_only=True, default='')
    profession_name = serializers.CharField(source='profession.name', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id',
            'name',
            'employee_number',
            'id_number',
            'status',
            'status_display',
            'department_name',
            'profession_name',
        ]
        read_only_fields = fields

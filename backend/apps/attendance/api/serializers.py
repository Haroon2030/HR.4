"""Serializers لوكيل البصمة."""
from rest_framework import serializers

MAX_PUNCHES_PER_REQUEST = 10_000
MAX_USERS_PER_REQUEST = 2_000


class AgentPunchSerializer(serializers.Serializer):
    device_user_id = serializers.IntegerField(min_value=1)
    punched_at = serializers.DateTimeField()
    punch_type = serializers.CharField(max_length=20, required=False, allow_blank=True)
    verify_mode = serializers.IntegerField(required=False, allow_null=True)
    raw_status = serializers.IntegerField(required=False, allow_null=True)
    device_record_uid = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    device_user_name = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AgentUserSerializer(serializers.Serializer):
    device_user_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    card = serializers.CharField(max_length=64, required=False, allow_blank=True)
    privilege = serializers.IntegerField(required=False, allow_null=True)


class AgentIngestSerializer(serializers.Serializer):
    device_id = serializers.IntegerField(min_value=1)
    agent_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    incremental = serializers.BooleanField(default=True)
    punches = AgentPunchSerializer(many=True, allow_empty=True)
    users = AgentUserSerializer(many=True, required=False)

    def validate_punches(self, value):
        if len(value) > MAX_PUNCHES_PER_REQUEST:
            raise serializers.ValidationError(
                f'الحد الأقصى {MAX_PUNCHES_PER_REQUEST} سجل في الطلب الواحد.'
            )
        return value

    def validate_users(self, value):
        if value and len(value) > MAX_USERS_PER_REQUEST:
            raise serializers.ValidationError(
                f'الحد الأقصى {MAX_USERS_PER_REQUEST} مستخدم في الطلب.'
            )
        return value

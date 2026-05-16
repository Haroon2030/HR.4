from django.urls import path

from apps.attendance.api.views import AgentDeviceListView, AgentIngestView

urlpatterns = [
    path('agent/devices/', AgentDeviceListView.as_view(), name='attendance-agent-devices'),
    path('agent/ingest/', AgentIngestView.as_view(), name='attendance-agent-ingest'),
]

from django.urls import path

from apps.attendance.api.views import (
    AgentDeviceListView,
    AgentIngestView,
    AgentPullRequestsView,
)

urlpatterns = [
    path('agent/devices/', AgentDeviceListView.as_view(), name='attendance-agent-devices'),
    path('agent/pull-requests/', AgentPullRequestsView.as_view(), name='attendance-agent-pull-requests'),
    path('agent/ingest/', AgentIngestView.as_view(), name='attendance-agent-ingest'),
]

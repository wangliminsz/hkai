# -*- coding: utf-8 -*-
from django.urls import path
from rest_framework import routers

from dvadmin.tenant.dashboard import DashboardStatView, EnvConfigView
from dvadmin.tenant.views import TenantViewSet
from dvadmin.tenant.workspace import (TenantHomeView, GroupNameRefreshView,
                                      SendReminderNowView, CalendarView)
from dvadmin.tenant.broadcast import (BroadcastPreviewView, BroadcastSendView,
                                      BroadcastStatusView, BroadcastCleanView)
from dvadmin.tenant.signup import SendSignupView, VerifySignupView

system_url = routers.SimpleRouter()
system_url.register(r'tenant', TenantViewSet)

urlpatterns = [
    path('admin/dashboard/', DashboardStatView.as_view()),
    path('admin/env/', EnvConfigView.as_view()),
    path('workspace/', TenantHomeView.as_view()),
    path('workspace/refresh_group_name/', GroupNameRefreshView.as_view()),
    path('workspace/send_reminder_now/', SendReminderNowView.as_view()),
    path('workspace/calendar/', CalendarView.as_view()),
    path('broadcast/preview/', BroadcastPreviewView.as_view()),
    path('broadcast/send/', BroadcastSendView.as_view()),
    path('broadcast/status/', BroadcastStatusView.as_view()),
    path('broadcast/clean/', BroadcastCleanView.as_view()),
    path('signup/send/', SendSignupView.as_view()),
    path('signup/verify/', VerifySignupView.as_view()),
]
urlpatterns += system_url.urls

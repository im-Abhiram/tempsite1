"""Thamarayyath Employee Portal — Attendance URL Configuration."""
from django.urls import path
from . import views

app_name = "attendance"

urlpatterns = [
    path("", views.DailyAttendanceDashboard.as_view(), name="daily_dashboard"),
    path("list/", views.AttendanceListView.as_view(), name="attendance_list"),
    path("quick-mark/", views.QuickAttendanceMarkView.as_view(), name="quick_mark"),
    path("mark/", views.AttendanceMarkView.as_view(), name="attendance_mark"),
    path("mark/<int:employee_pk>/", views.AttendanceMarkView.as_view(), name="attendance_mark_emp"),
    path("<int:pk>/", views.AttendanceDetailView.as_view(), name="attendance_detail"),
    path("<int:pk>/correct/", views.AttendanceCorrectionView.as_view(), name="attendance_correct"),
    path("holidays/", views.HolidayListView.as_view(), name="holiday_list"),
    path("holidays/add/", views.HolidayCreateView.as_view(), name="holiday_create"),
    path("holidays/<int:pk>/delete/", views.HolidayDeleteView.as_view(), name="holiday_delete"),
    # Leaves
    path("leaves/", views.LeaveListView.as_view(), name="leave_list"),
    path("leaves/add/", views.LeaveCreateView.as_view(), name="leave_create"),
    path("leaves/<int:pk>/status/", views.LeaveStatusUpdateView.as_view(), name="leave_status"),
]

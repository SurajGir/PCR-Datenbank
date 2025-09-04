from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.inventory, name='inventory'),
    path('sample/<str:sample_id>/', views.sample_detail, name='sample_detail'),
    path('sample/<str:sample_id>/edit/', views.edit_sample, name='edit_sample'),
    path('sample/<str:sample_id>/delete/', views.delete_sample, name='delete_sample'),
    path('add/', views.add_sample, name='add_sample'),
    path('settings/', views.settings, name='settings'),
    path('settings/delete-option/', views.delete_option, name='delete_option'),
    path('mark-finished/', views.mark_samples_finished, name='mark_finished'),
    path('export/', views.export_samples, name='export_samples'),
    path('import/', views.import_samples, name='import'),
    path('samples/mark-finished/', views.mark_samples_finished, name='mark_samples_finished'),
    path('download-template/', views.download_template, name='download_template'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('storage-places/', views.get_storage_places, name='get_storage_places'),
    path('manage-storage/', views.manage_storage, name='manage_storage'),
    path('exported-list/', views.exported_list, name='exported_list'),
    path('samples/mark-not-found/', views.mark_samples_not_found, name='mark_samples_not_found'),
    path('mark-in-use/', views.mark_in_use, name='mark_in_use'),
    path('samples/mark-finished/', views.mark_samples_finished, name='mark_samples_finished'),
    path('samples/refresh/', views.refresh_samples, name='refresh_samples'),
    path('record-active-use/', views.record_active_use, name='record_active_use'),
    path('samples/make-available/', views.mark_samples_available, name='mark_samples_available'),
    path('create-target/', views.create_target, name='create_target'),
]
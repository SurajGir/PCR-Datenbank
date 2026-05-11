from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group
from .models import UsageLog, PCRSample

# Remove Groups - you don't need them
admin.site.unregister(Group)


# Custom User admin with better password management
class CustomUserAdmin(UserAdmin):
    list_display = (
    'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined', 'last_login')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)

    fieldsets = UserAdmin.fieldsets + (
        ('Password Management', {
            'fields': (),
            'description': 'To change this user\'s password, use the "Change password" link in the top right of this form.'
        }),
    )


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    # Added volume_unit so you can see exactly what was deducted!
    list_display = ('sample', 'user', 'checkout_date', 'return_date', 'volume_used', 'volume_unit', 'notes')
    list_filter = ('checkout_date', 'return_date', 'user')
    search_fields = ('sample__mikrogen_internal_number', 'user__username', 'notes')
    date_hierarchy = 'checkout_date'
    readonly_fields = ('checkout_date',)
    list_per_page = 50


@admin.register(PCRSample)
class PCRSampleAdmin(admin.ModelAdmin):
    # Added volume_unit and active_use to the overview columns
    list_display = (
        'mikrogen_internal_number', 'provider_number', 'provider', 'target',
        'sample_type', 'storage_place', 'sample_volume', 'sample_volume_remaining',
        'volume_unit', 'in_use', 'active_use', 'current_user'
    )

    # Added volume_unit and active_use to the sidebar filters
    list_filter = (
        'in_use', 'active_use', 'not_found', 'volume_unit', 'target',
        'sample_type', 'provider', 'storage_place', 'extractor', 'cycler'
    )

    search_fields = (
        'mikrogen_internal_number', 'provider_number', 'country_of_origin', 'notes', 'positive_for', 'negative_for'
    )

    date_hierarchy = 'date_added'
    readonly_fields = ('date_added', 'last_modified')
    list_per_page = 50

    # Fieldsets create beautiful visual sections in the admin edit page!
    fieldsets = (
        ('Core Identifiers', {
            'fields': ('mikrogen_internal_number', 'provider_number', 'target', 'storage_place')
        }),
        ('Target Status', {
            'fields': ('positive_for', 'negative_for')
        }),
        ('Sample & Patient Demographics', {
            'fields': ('provider', 'sample_type', 'date_of_draw', 'age', 'gender', 'country_of_origin')
        }),
        ('Lab Processing', {
            'fields': (
            'extraction_date', 'extractor', 'cycler', 'mikrogen_pcr_kit', 'external_pcr_kit', 'mikrogen_ct_value',
            'external_ct_value')
        }),
        ('Inventory & Volumes', {
            'fields': ('sample_volume', 'sample_volume_remaining', 'volume_unit', 'notes')
        }),
        ('System Tracking', {
            'fields': ('current_user', 'in_use', 'active_use', 'not_found', 'added_by')
        }),
        ('Timestamps', {
            'fields': ('date_added', 'last_modified')
        }),
    )
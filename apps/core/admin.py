from django.contrib import admin
from .models import (
    PCRSample, Provider, Target, SampleType, PCRKit,
    StoragePlace, Extractor, Cycler, UsageLog
)

@admin.register(PCRSample)
class PCRSampleAdmin(admin.ModelAdmin):
    list_display = ('mikrogen_internal_number', 'provider', 'target', 'sample_type',
                    'sample_volume_remaining', 'in_use', 'current_user')
    list_filter = ('in_use', 'target', 'sample_type', 'provider')
    search_fields = ('mikrogen_internal_number', 'provider_number')
    date_hierarchy = 'date_added'

@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = ('sample', 'user', 'checkout_date', 'return_date', 'volume_used')
    list_filter = ('user',)
    date_hierarchy = 'checkout_date'

# Register simple models
admin.site.register(Provider)
admin.site.register(Target)
admin.site.register(SampleType)
admin.site.register(StoragePlace)
admin.site.register(Extractor)
admin.site.register(Cycler)

@admin.register(PCRKit)
class PCRKitAdmin(admin.ModelAdmin):
    list_display = ('name', 'type')
    list_filter = ('type',)
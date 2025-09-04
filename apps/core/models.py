from django.db import models
from django.contrib.auth.models import User


class Provider(models.Model):
    """Model for sample providers"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Target(models.Model):
    """Model for PCR targets"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class SampleType(models.Model):
    """Model for sample types"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class PCRKit(models.Model):
    """Model for PCR kits"""
    TYPE_CHOICES = (
        ('mikrogen', 'Mikrogen'),
        ('external', 'External'),
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    class Meta:
        unique_together = ['name', 'type']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class StoragePlace(models.Model):
    """Model for storage places with hierarchical structure"""
    STORAGE_TYPES = (
        ('room', 'Room'),
        ('freezer', 'Freezer'),
        ('drawer', 'Drawer'),
        ('box', 'Box'),
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=STORAGE_TYPES)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

class Extractor(models.Model):
    """Model for extractors"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Cycler(models.Model):
    """Model for PCR cyclers"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class PCRSample(models.Model):
    """Model for PCR samples in the database"""
    # General information
    mikrogen_internal_number = models.CharField(max_length=50, unique=True)
    provider_number = models.CharField(max_length=50, blank=True, null=True)
    target = models.ForeignKey(Target, on_delete=models.PROTECT)
    storage_place = models.ForeignKey(StoragePlace, on_delete=models.SET_NULL, null=True, blank=True)

    # Sample information
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT)
    date_of_draw = models.DateField(null=True, blank=True)
    GENDER_CHOICES = (
        ('male', 'Male'),
        ('female', 'Female'),
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True, null=True)

    # Extraction information
    extraction_date = models.DateField(null=True, blank=True)
    extractor = models.ForeignKey(Extractor, on_delete=models.SET_NULL, null=True, blank=True)

    # PCR details
    cycler = models.ForeignKey(Cycler, on_delete=models.SET_NULL, null=True, blank=True)
    mikrogen_pcr_kit = models.ForeignKey(PCRKit, on_delete=models.PROTECT,
                                         related_name='mikrogen_samples',
                                         limit_choices_to={'type': 'mikrogen'},
                                         blank=True, null=True)
    external_pcr_kit = models.ForeignKey(PCRKit, on_delete=models.PROTECT,
                                         related_name='external_samples',
                                         limit_choices_to={'type': 'external'},
                                         blank=True, null=True)
    mikrogen_ct_value = models.FloatField(blank=True, null=True)
    external_ct_value = models.FloatField(blank=True, null=True)

    # Volume tracking
    sample_volume = models.FloatField(help_text="Sample volume in ml")
    sample_volume_remaining = models.FloatField(help_text="Remaining sample volume in ml")

    # Usage tracking
    current_user = models.ForeignKey(User, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name='samples_in_use')
    in_use = models.BooleanField(default=False)
    not_found = models.BooleanField(default=False)
    active_use = models.BooleanField(default=False)

    # Metadata
    date_added = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                 null=True, related_name='added_samples')

    # Notes
    notes = models.TextField(blank=True, null=True)

    positive_for = models.TextField(blank=True, null=True)
    negative_for = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Sample {self.mikrogen_internal_number}"

    def mark_in_use(self, user):
        self.current_user = user
        self.in_use = True
        self.save()

    def mark_finished(self, volume_used=0):
        self.current_user = None
        self.in_use = False
        if volume_used > 0:
            self.sample_volume_remaining -= volume_used
            if self.sample_volume_remaining < 0:
                self.sample_volume_remaining = 0
        self.save()

    @property
    def is_reserved(self):
        """Returns True if sample is reserved but not actively being used"""
        return self.in_use and self.current_user and not self.not_found


class UsageLog(models.Model):
    """Model to track sample usage history"""
    sample = models.ForeignKey(PCRSample, on_delete=models.CASCADE, related_name='usage_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    volume_used = models.FloatField(default=0)
    checkout_date = models.DateTimeField(auto_now_add=True)
    return_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.sample} used by {self.user.username}"
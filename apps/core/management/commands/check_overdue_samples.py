from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from apps.core.models import PCRSample
from datetime import timedelta


class Command(BaseCommand):
    help = 'Checks for samples that have been reserved/in use for more than 2 weeks and sends email notifications'

    def handle(self, *args, **options):
        # Calculate the date 2 weeks ago
        two_weeks_ago = timezone.now() - timedelta(days=14)

        # Get all users with reserved samples
        users_with_samples = User.objects.filter(
            samples_in_use__in_use=True,  # Using the related_name from your model
            samples_in_use__last_modified__lt=two_weeks_ago
        ).distinct()

        self.stdout.write(f"Found {users_with_samples.count()} users with overdue samples")

        # Process each user
        for user in users_with_samples:
            # Get this user's overdue samples
            overdue_samples = PCRSample.objects.filter(
                current_user=user,
                in_use=True,
                last_modified__lt=two_weeks_ago
            )

            # Skip if no overdue samples (shouldn't happen due to our query, but just in case)
            if not overdue_samples.exists():
                continue

            # Count samples by status
            reserved_count = overdue_samples.filter(active_use=False).count()
            in_use_count = overdue_samples.filter(active_use=True).count()

            # Prepare email content
            subject = 'PCR Database: Samples Reserved for Over 2 Weeks'
            message = f"""
Hello {user.first_name or user.username},

This is an automated notification from the PCR Database system.

You currently have samples that have been in your list for more than 2 weeks:
- {reserved_count} samples with status "Reserved"
- {in_use_count} samples with status "In Use"

Please take action by either:
1. Marking samples as "Not Found" if you cannot locate them
2. Deducting used volume if you've used the samples
3. Making samples available if you're finished with them

You can manage your samples here: http://pcrdatabase.example.com/exported-list/

Thank you,
PCR Database System
"""

            # Send the email
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Sent email to {user.email} about {overdue_samples.count()} overdue samples"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to send email to {user.email}: {str(e)}"))
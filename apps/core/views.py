from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Count, F, ExpressionWrapper, FloatField
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
import os
import json
import csv
import pandas as pd
from datetime import datetime
from io import BytesIO
from django.views.decorators.http import require_POST
from apps.core.models import StoragePlace

from .models import (
    PCRSample, Provider, Target, SampleType, PCRKit,
    StoragePlace, Extractor, Cycler, UsageLog
)


@login_required
def dashboard(request):
    """Dashboard view with statistics and charts"""
    # Basic statistics
    total_samples = PCRSample.objects.count()
    in_use_count = PCRSample.objects.filter(in_use=True).count()
    available_count = total_samples - in_use_count

    # Low volume samples (less than 25% remaining)
    low_volume_samples = PCRSample.objects.annotate(
        percentage=ExpressionWrapper(
            F('sample_volume_remaining') * 100 / F('sample_volume'),
            output_field=FloatField()
        )
    ).filter(percentage__lt=25).count()

    # Sample type distribution
    sample_type_data = list(PCRSample.objects.values('sample_type__name')
                            .annotate(count=Count('id'))
                            .order_by('-count')[:10])

    sample_type_labels = json.dumps([item['sample_type__name'] for item in sample_type_data])
    sample_type_counts = [item['count'] for item in sample_type_data]

    # Target distribution
    target_data = list(PCRSample.objects.values('target__name')
                       .annotate(count=Count('id'))
                       .order_by('-count')[:10])

    target_labels = json.dumps([item['target__name'] for item in target_data])
    target_counts = [item['count'] for item in target_data]

    # Recent activity
    recent_logs = UsageLog.objects.select_related('sample', 'user').order_by('-checkout_date')[:10]

    # Prepare activity logs
    for log in recent_logs:
        if log.return_date:
            log.action_type = "returned"
        else:
            log.action_type = "checked out"
        log.timestamp = log.return_date if log.return_date else log.checkout_date

    # Top users
    top_users = User.objects.annotate(
        usage_count=Count('usagelog')
    ).order_by('-usage_count')[:5]

    context = {
        'total_samples': total_samples,
        'in_use_count': in_use_count,
        'available_count': available_count,
        'low_volume_count': low_volume_samples,
        'sample_type_labels': sample_type_labels,
        'sample_type_data': sample_type_counts,
        'target_labels': target_labels,
        'target_data': target_counts,
        'recent_logs': recent_logs,
        'top_users': top_users,
    }

    return render(request, 'core/dashboard.html', context)


@login_required
def inventory(request):
    """Main inventory page with filtering options"""
    # Get all filter options for dropdowns
    targets = Target.objects.all()
    sample_types = SampleType.objects.all()

    # Apply filters if provided
    target_id = request.GET.get('target', '')
    sample_type_id = request.GET.get('sample_type', '')
    min_ct = request.GET.get('min_ct', '0')
    max_ct = request.GET.get('max_ct', '50')
    min_volume = request.GET.get('min_volume', '0')
    max_volume = request.GET.get('max_volume', '1000')

    # Add advanced filters
    positive_target_id = request.GET.get('positive_target', '')
    negative_target_id = request.GET.get('negative_target', '')

    # Start with all samples
    samples = PCRSample.objects.all().order_by('mikrogen_internal_number')

    # Search functionality
    search_term = request.GET.get('search', '')
    if search_term:
        samples = samples.filter(
            Q(mikrogen_internal_number__icontains=search_term) |
            Q(provider_number__icontains=search_term) |
            Q(provider__name__icontains=search_term) |
            Q(target__name__icontains=search_term) |
            Q(sample_type__name__icontains=search_term) |
            Q(mikrogen_pcr_kit__name__icontains=search_term) |
            Q(external_pcr_kit__name__icontains=search_term) |
            Q(notes__icontains=search_term)
        )

    # Apply basic filters
    if target_id:
        samples = samples.filter(target_id=target_id)
    if sample_type_id:
        samples = samples.filter(sample_type_id=sample_type_id)

    # Apply advanced filters for positive/negative targets
    if positive_target_id:
        positive_target = Target.objects.get(id=positive_target_id)
        samples = samples.filter(positive_for__icontains=positive_target.name)

    if negative_target_id:
        negative_target = Target.objects.get(id=negative_target_id)
        samples = samples.filter(negative_for__icontains=negative_target.name)

    # Apply CT value filters only if they differ from defaults
    if min_ct and min_ct != '0' or max_ct and max_ct != '50':
        ct_filters = Q()

        # Handle Mikrogen CT values
        mikrogen_filter = Q()
        if min_ct and min_ct != '0':
            mikrogen_filter &= Q(mikrogen_ct_value__gte=float(min_ct))
        if max_ct and max_ct != '50':
            mikrogen_filter &= Q(mikrogen_ct_value__lte=float(max_ct))

        # Only apply mikrogen filter if there's a valid condition
        if mikrogen_filter != Q():
            ct_filters |= mikrogen_filter

        # Handle External CT values
        external_filter = Q()
        if min_ct and min_ct != '0':
            external_filter &= Q(external_ct_value__gte=float(min_ct))
        if max_ct and max_ct != '50':
            external_filter &= Q(external_ct_value__lte=float(max_ct))

        # Only apply external filter if there's a valid condition
        if external_filter != Q():
            ct_filters |= external_filter

        # Apply combined filter only if we have conditions to filter on
        if ct_filters != Q():
            samples = samples.filter(ct_filters)

    # Apply volume filters only if they differ from defaults
    if min_volume and min_volume != '0' or max_volume and max_volume != '1000':
        volume_filter = Q()
        if min_volume and min_volume != '0':
            volume_filter &= Q(sample_volume_remaining__gte=float(min_volume))
        if max_volume and max_volume != '1000':
            volume_filter &= Q(sample_volume_remaining__lte=float(max_volume))

        if volume_filter != Q():
            samples = samples.filter(volume_filter)

    # Add volume percentage for each sample
    for sample in samples:
        if sample.sample_volume > 0:
            sample.volume_percentage = (sample.sample_volume_remaining / sample.sample_volume) * 100
        else:
            sample.volume_percentage = 0

    # Print debug info to console for troubleshooting
    print(
        f"Filters applied: target={target_id}, sample_type={sample_type_id}, "
        f"positive={positive_target_id}, negative={negative_target_id}, "
        f"CT={min_ct}-{max_ct}, volume={min_volume}-{max_volume}")
    print(f"Results: {samples.count()} samples found")

    context = {
        'samples': samples,
        'targets': targets,
        'sample_types': sample_types,
        'filters': {
            'target': target_id,
            'sample_type': sample_type_id,
            'min_ct': min_ct,
            'max_ct': max_ct,
            'min_volume': min_volume,
            'max_volume': max_volume,
            'positive_target': positive_target_id,
            'negative_target': negative_target_id
        },
        'search_term': search_term,
        'results_count': samples.count()
    }

    return render(request, 'core/inventory.html', context)

@login_required
def sample_detail(request, sample_id):
    """View for displaying all details of a sample"""
    sample = get_object_or_404(PCRSample, mikrogen_internal_number=sample_id)
    usage_logs = sample.usage_logs.all().order_by('-checkout_date')

    # Build storage location full path
    storage_path = []
    if sample.storage_place:
        current = sample.storage_place
        while current:
            storage_path.insert(0, current.name)
            current = current.parent

    sample.positive_targets = sample.positive_for.split(',') if sample.positive_for else []
    sample.negative_targets = sample.negative_for.split(',') if sample.negative_for else []

    context = {
        'sample': sample,
        'usage_logs': usage_logs,
        'storage_path': ' → '.join(storage_path) if storage_path else 'Not specified'
    }

    return render(request, 'core/sample_detail.html', context)


@login_required
def get_storage_places(request):
    """API endpoint to get storage places by type and parent"""
    storage_type = request.GET.get('type')
    parent_id = request.GET.get('parent')

    # Different query depending on parameters
    if storage_type and parent_id:
        # Filter by both type and parent
        places = StoragePlace.objects.filter(
            type=storage_type,
            parent_id=parent_id
        ).values('id', 'name')
    elif storage_type:
        # Filter just by type when no parent is specified
        places = StoragePlace.objects.filter(
            type=storage_type
        ).values('id', 'name')
    else:
        places = []

    return JsonResponse(list(places), safe=False)


@login_required
@user_passes_test(lambda u: u.is_staff)  # Only staff can access
def manage_storage(request):
    """Page for managing storage locations"""

    if request.method == 'POST':
        # Handle storage place movement
        action = request.POST.get('action')

        if action == 'move':
            item_id = request.POST.get('item_id')
            new_parent_id = request.POST.get('new_parent_id')

            item = get_object_or_404(StoragePlace, id=item_id)

            # Prevent circular references
            if new_parent_id:
                new_parent = get_object_or_404(StoragePlace, id=new_parent_id)

                # Check if new_parent is a descendant of item
                current = new_parent
                while current:
                    if current.id == item.id:
                        messages.error(request, "Cannot move a storage location into its own descendant.")
                        return redirect('core:manage_storage')
                    current = current.parent

                # Check if the new parent is of the correct type
                if item.type == 'freezer' and new_parent.type != 'room':
                    messages.error(request, "Freezers can only be placed in rooms.")
                elif item.type == 'drawer' and new_parent.type != 'freezer':
                    messages.error(request, "Drawers can only be placed in freezers.")
                elif item.type == 'box' and new_parent.type != 'drawer':
                    messages.error(request, "Boxes can only be placed in drawers.")
                else:
                    item.parent = new_parent
                    item.save()
                    messages.success(request, f"{item.name} moved successfully.")
            else:
                # Moving to top level (only rooms should be at top level)
                if item.type != 'room':
                    messages.error(request, "Only rooms can be at the top level.")
                else:
                    item.parent = None
                    item.save()
                    messages.success(request, f"{item.name} moved to top level.")

        elif action == 'add':
            name = request.POST.get('name')
            type_value = request.POST.get('type')
            parent_id = request.POST.get('parent_id')

            if not name or not type_value:
                messages.error(request, "Name and type are required.")
            else:
                parent = None
                if parent_id:
                    parent = get_object_or_404(StoragePlace, id=parent_id)

                # Validate parent type
                if type_value == 'freezer' and (not parent or parent.type != 'room'):
                    messages.error(request, "Freezers must be placed in rooms.")
                elif type_value == 'drawer' and (not parent or parent.type != 'freezer'):
                    messages.error(request, "Drawers must be placed in freezers.")
                elif type_value == 'box' and (not parent or parent.type != 'drawer'):
                    messages.error(request, "Boxes must be placed in drawers.")
                elif type_value == 'room' and parent:
                    messages.error(request, "Rooms cannot have a parent.")
                else:
                    StoragePlace.objects.create(name=name, type=type_value, parent=parent)
                    messages.success(request, f"New {type_value} '{name}' added successfully.")

        elif action == 'delete':
            item_id = request.POST.get('item_id')

            try:
                item = StoragePlace.objects.get(id=item_id)

                # Check if the storage place is in use
                if PCRSample.objects.filter(storage_place=item).exists():
                    messages.error(request, f"Cannot delete {item.name} because it contains samples.")
                elif StoragePlace.objects.filter(parent=item).exists():
                    messages.error(request, f"Cannot delete {item.name} because it contains other storage locations.")
                else:
                    name = item.name
                    item.delete()
                    messages.success(request, f"{name} deleted successfully.")
            except StoragePlace.DoesNotExist:
                messages.error(request, "Storage place not found.")

    # Get all storage places organized hierarchically
    rooms = StoragePlace.objects.filter(type='room').order_by('name')

    storage_hierarchy = []
    for room in rooms:
        room_item = {
            'id': room.id,
            'name': room.name,
            'type': room.type,
            'freezers': []
        }

        freezers = StoragePlace.objects.filter(type='freezer', parent=room)
        for freezer in freezers:
            freezer_item = {
                'id': freezer.id,
                'name': freezer.name,
                'type': freezer.type,
                'drawers': []
            }

            drawers = StoragePlace.objects.filter(type='drawer', parent=freezer)
            for drawer in drawers:
                drawer_item = {
                    'id': drawer.id,
                    'name': drawer.name,
                    'type': drawer.type,
                    'boxes': []
                }

                boxes = StoragePlace.objects.filter(type='box', parent=drawer)
                for box in boxes:
                    drawer_item['boxes'].append({
                        'id': box.id,
                        'name': box.name,
                        'type': box.type
                    })

                freezer_item['drawers'].append(drawer_item)

            room_item['freezers'].append(freezer_item)

        storage_hierarchy.append(room_item)

    context = {
        # other context variables
        'storage_hierarchy': storage_hierarchy,
        'rooms': rooms,
        'storage_types': StoragePlace.STORAGE_TYPES
    }

    return render(request, 'core/manage_storage.html', context)

@login_required
def add_sample(request):
    """View for adding a new sample"""
    if request.method == 'POST':
        # Process form data - get required fields
        mikrogen_internal_number = request.POST.get('mikrogen_internal_number')
        provider_id = request.POST.get('provider')
        target_id = request.POST.get('target')
        sample_type_id = request.POST.get('sample_type')
        sample_volume = request.POST.get('sample_volume')

        # Create new sample with required fields
        sample = PCRSample(
            mikrogen_internal_number=mikrogen_internal_number,
            provider_id=provider_id,
            target_id=target_id,
            sample_type_id=sample_type_id,
            sample_volume=float(sample_volume),
            sample_volume_remaining=float(sample_volume),
            added_by=request.user
        )

        # For storage place, get the most specific one provided
        storage_place_id = (
                request.POST.get('box') or
                request.POST.get('drawer') or
                request.POST.get('freezer') or
                request.POST.get('room')
        )
        if storage_place_id:
            sample.storage_place_id = storage_place_id

        # Handle other optional fields
        optional_fields = [
            'provider_number', 'date_of_draw',
            'age', 'gender', 'country_of_origin', 'extraction_date',
            'extractor', 'cycler', 'mikrogen_pcr_kit', 'external_pcr_kit',
            'mikrogen_ct_value', 'external_ct_value', 'notes'
        ]

        for field in optional_fields:
            value = request.POST.get(field)
            if value:
                # Convert date strings to date objects
                if field in ['date_of_draw', 'extraction_date'] and value:
                    value = datetime.strptime(value, '%Y-%m-%d').date()

                # Convert numeric values
                if field in ['age', 'mikrogen_ct_value', 'external_ct_value']:
                    if value:
                        value = float(value) if '.' in value else int(value)

                setattr(sample, field, value)

        positive_targets = request.POST.getlist('positive_targets', [])
        negative_targets = request.POST.getlist('negative_targets', [])

        if positive_targets:
            sample.positive_for = ', '.join(positive_targets)
        if negative_targets:
            sample.negative_for = ', '.join(negative_targets)

        sample.save()
        messages.success(request, f"Sample {mikrogen_internal_number} added successfully.")
        return redirect('core:inventory')

    # GET request - show form
    # Prepare storage places by type
    rooms = StoragePlace.objects.filter(type='room', parent=None)

    context = {
        'providers': Provider.objects.all(),
        'targets': Target.objects.all(),
        'sample_types': SampleType.objects.all(),
        'rooms': rooms,  # Only rooms for initial load
        'extractors': Extractor.objects.all(),
        'cyclers': Cycler.objects.all(),
        'mikrogen_kits': PCRKit.objects.filter(type='mikrogen'),
        'external_kits': PCRKit.objects.filter(type='external'),
    }

    return render(request, 'core/add_sample.html', context)


@require_POST
@login_required
def create_target(request):
    """Create a new target via AJAX"""
    try:
        data = json.loads(request.body)
        name = data.get('name')

        if not name:
            return JsonResponse({'success': False, 'error': 'Target name is required'})

        # Check if target already exists
        if Target.objects.filter(name=name).exists():
            return JsonResponse({'success': False, 'error': 'Target already exists'})

        # Create new target
        Target.objects.create(name=name)

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def edit_sample(request, sample_id):
    """View for editing an existing sample"""
    sample = get_object_or_404(PCRSample, mikrogen_internal_number=sample_id)

    # Get current storage place and its hierarchy
    selected_box = None
    selected_drawer = None
    selected_freezer = None
    selected_room = None

    if sample.storage_place:
        current_place = sample.storage_place
        if current_place.type == 'box':
            selected_box = current_place
            selected_drawer = current_place.parent
            selected_freezer = selected_drawer.parent if selected_drawer else None
            selected_room = selected_freezer.parent if selected_freezer else None
        elif current_place.type == 'drawer':
            selected_drawer = current_place
            selected_freezer = current_place.parent
            selected_room = selected_freezer.parent if selected_freezer else None
        elif current_place.type == 'freezer':
            selected_freezer = current_place
            selected_room = current_place.parent
        elif current_place.type == 'room':
            selected_room = current_place

    if request.method == 'POST':
        # Process form data - update fields
        sample.provider_id = request.POST.get('provider')
        sample.target_id = request.POST.get('target')
        sample.sample_type_id = request.POST.get('sample_type')

        positive_target_names = request.POST.getlist('positive_targets')
        negative_target_names = request.POST.getlist('negative_targets')

        sample.positive_for = ','.join(positive_target_names)
        sample.negative_for = ','.join(negative_target_names)

        # Volume needs special handling to track history
        new_volume = float(request.POST.get('sample_volume', 0))
        if new_volume != sample.sample_volume:
            # If total volume increases, also increase the remaining volume
            volume_diff = new_volume - sample.sample_volume
            sample.sample_volume = new_volume
            sample.sample_volume_remaining += volume_diff
            if sample.sample_volume_remaining < 0:
                sample.sample_volume_remaining = 0

        # For storage place, get the most specific one provided
        storage_place_id = (
                request.POST.get('box') or
                request.POST.get('drawer') or
                request.POST.get('freezer') or
                request.POST.get('room')
        )
        if storage_place_id:
            sample.storage_place_id = storage_place_id
        else:
            sample.storage_place = None

        # Handle other optional fields
        optional_fields = [
            'provider_number', 'date_of_draw',
            'age', 'gender', 'country_of_origin', 'extraction_date',
            'extractor', 'cycler', 'mikrogen_pcr_kit', 'external_pcr_kit',
            'mikrogen_ct_value', 'external_ct_value', 'notes'
        ]

        for field in optional_fields:
            value = request.POST.get(field, '')

            # Handle foreign keys with empty values
            if field in ['extractor', 'cycler', 'mikrogen_pcr_kit', 'external_pcr_kit'] and not value:
                setattr(sample, field, None)
                continue

            if value:
                # Convert date strings to date objects
                if field in ['date_of_draw', 'extraction_date']:
                    value = datetime.strptime(value, '%Y-%m-%d').date()

                # Convert numeric values
                if field in ['age', 'mikrogen_ct_value', 'external_ct_value']:
                    value = float(value) if '.' in value else int(value)

                setattr(sample, field, value)
            elif field not in ['notes', 'provider_number', 'country_of_origin']:
                # Clear values for non-text fields
                setattr(sample, field, None)

        sample.save()
        messages.success(request, f"Sample {sample_id} updated successfully.")
        return redirect('core:sample_detail', sample_id=sample_id)

    # GET request - show form with existing data
    # Get all rooms
    rooms = StoragePlace.objects.filter(type='room', parent=None)

    # Get freezers if a room is selected
    freezers = []
    if selected_room:
        freezers = StoragePlace.objects.filter(type='freezer', parent=selected_room)

    # Get drawers if a freezer is selected
    drawers = []
    if selected_freezer:
        drawers = StoragePlace.objects.filter(type='drawer', parent=selected_freezer)

    # Get boxes if a drawer is selected
    boxes = []
    if selected_drawer:
        boxes = StoragePlace.objects.filter(type='box', parent=selected_drawer)

    context = {
        'sample': sample,
        'providers': Provider.objects.all(),
        'targets': Target.objects.all(),
        'sample_types': SampleType.objects.all(),
        'rooms': rooms,
        'freezers': freezers,
        'drawers': drawers,
        'boxes': boxes,
        'selected_room': selected_room,
        'selected_freezer': selected_freezer,
        'selected_drawer': selected_drawer,
        'selected_box': selected_box,
        'extractors': Extractor.objects.all(),
        'cyclers': Cycler.objects.all(),
        'mikrogen_kits': PCRKit.objects.filter(type='mikrogen'),
        'external_kits': PCRKit.objects.filter(type='external'),
    }

    if sample.positive_for:
        sample.positive_targets = [t.strip() for t in sample.positive_for.split(',') if t.strip()]
    else:
        sample.positive_targets = []

    if sample.negative_for:
        sample.negative_targets = [t.strip() for t in sample.negative_for.split(',') if t.strip()]
    else:
        sample.negative_targets = []

    return render(request, 'core/edit_sample.html', context)

@login_required
def delete_sample(request, sample_id):
    """Delete a sample"""
    if request.method == 'POST':
        sample = get_object_or_404(PCRSample, mikrogen_internal_number=sample_id)
        sample.delete()
        messages.success(request, f"Sample {sample_id} deleted successfully.")
        return redirect('core:inventory')

    return redirect('core:sample_detail', sample_id=sample_id)


@login_required
def settings(request):
    """Settings page for managing dropdown options"""
    # Get the section from the URL parameter
    section = request.GET.get('section', 'targets')  # Default to targets

    # Handle form submissions for adding/editing/deleting options
    if request.method == 'POST':
        action = request.POST.get('action')
        option_type = request.POST.get('option_type')

        if action == 'add':
            name = request.POST.get('name')
            if not name:
                messages.error(request, "Name cannot be empty.")
            else:
                if option_type == 'target':
                    Target.objects.create(name=name)
                    messages.success(request, f"Target '{name}' added successfully.")
                elif option_type == 'sample_type':
                    SampleType.objects.create(name=name)
                    messages.success(request, f"Sample type '{name}' added successfully.")
                elif option_type == 'provider':
                    Provider.objects.create(name=name)
                    messages.success(request, f"Provider '{name}' added successfully.")
                elif option_type == 'extractor':
                    Extractor.objects.create(name=name)
                    messages.success(request, f"Extractor '{name}' added successfully.")
                elif option_type == 'cycler':
                    Cycler.objects.create(name=name)
                    messages.success(request, f"Cycler '{name}' added successfully.")
                elif option_type == 'pcr_kit':
                    kit_type = request.POST.get('kit_type', 'mikrogen')
                    PCRKit.objects.create(name=name, type=kit_type)
                    messages.success(request, f"PCR Kit '{name}' added successfully.")
                elif option_type == 'storage_place':
                    storage_type = request.POST.get('type')
                    parent_id = request.POST.get('parent_id')

                    # Add debug prints
                    print(f"DEBUG: Adding storage place - name: {name}, type: {storage_type}, parent_id: {parent_id}")

                    parent = None
                    if parent_id:
                        try:
                            parent = StoragePlace.objects.get(id=parent_id)
                            print(f"DEBUG: Found parent: {parent.name}")
                        except StoragePlace.DoesNotExist:
                            print(f"DEBUG: Parent with ID {parent_id} not found")
                            parent = None

                    new_storage = StoragePlace.objects.create(name=name, type=storage_type, parent=parent)
                    print(f"DEBUG: Created storage place: {new_storage.id}")
                    messages.success(request, f"{storage_type.capitalize()} '{name}' added successfully.")

        elif action == 'edit':
            option_id = request.POST.get('option_id')
            name = request.POST.get('name')

            if not name:
                messages.error(request, "Name cannot be empty.")
            else:
                if option_type == 'target':
                    target = get_object_or_404(Target, id=option_id)
                    target.name = name
                    target.save()
                    messages.success(request, f"Target updated successfully.")
                elif option_type == 'sample_type':
                    sample_type = get_object_or_404(SampleType, id=option_id)
                    sample_type.name = name
                    sample_type.save()
                    messages.success(request, f"Sample type updated successfully.")
                elif option_type == 'provider':
                    provider = get_object_or_404(Provider, id=option_id)
                    provider.name = name
                    provider.save()
                    messages.success(request, f"Provider updated successfully.")
                elif option_type == 'extractor':
                    extractor = get_object_or_404(Extractor, id=option_id)
                    extractor.name = name
                    extractor.save()
                    messages.success(request, f"Extractor updated successfully.")
                elif option_type == 'cycler':
                    cycler = get_object_or_404(Cycler, id=option_id)
                    cycler.name = name
                    cycler.save()
                    messages.success(request, f"Cycler updated successfully.")
                elif option_type == 'pcr_kit':
                    kit = get_object_or_404(PCRKit, id=option_id)
                    kit.name = name
                    kit_type = request.POST.get('kit_type')
                    if kit_type:
                        kit.type = kit_type
                    kit.save()
                    messages.success(request, f"PCR Kit updated successfully.")

        elif action == 'move':
            item_id = request.POST.get('item_id')
            new_parent_id = request.POST.get('new_parent_id')

            item = get_object_or_404(StoragePlace, id=item_id)

            # Prevent circular references
            if new_parent_id:
                new_parent = get_object_or_404(StoragePlace, id=new_parent_id)

                # Check if new_parent is a descendant of item
                current = new_parent
                while current:
                    if current.id == item.id:
                        messages.error(request, "Cannot move a storage location into its own descendant.")
                        return redirect(f'/settings/?section={section}')
                    current = current.parent

                # Check if the new parent is of the correct type
                if item.type == 'freezer' and new_parent.type != 'room':
                    messages.error(request, "Freezers can only be placed in rooms.")
                elif item.type == 'drawer' and new_parent.type != 'freezer':
                    messages.error(request, "Drawers can only be placed in freezers.")
                elif item.type == 'box' and new_parent.type != 'drawer':
                    messages.error(request, "Boxes can only be placed in drawers.")
                else:
                    item.parent = new_parent
                    item.save()
                    messages.success(request, f"{item.name} moved successfully.")
            else:
                # Moving to top level (only rooms should be at top level)
                if item.type != 'room':
                    messages.error(request, "Only rooms can be at the top level.")
                else:
                    item.parent = None
                    item.save()
                    messages.success(request, f"{item.name} moved to top level.")

        elif action == 'delete':
            item_id = request.POST.get('item_id')

            if not item_id:  # Add this check
                messages.error(request, "No item ID provided for deletion.")
                return redirect(f'/settings/?section={section}')

            try:
                if option_type == 'target':
                    target = get_object_or_404(Target, id=option_id)
                    name = target.name
                    target.delete()
                    messages.success(request, f"Target '{name}' deleted successfully.")
                elif option_type == 'sample_type':
                    sample_type = get_object_or_404(SampleType, id=option_id)
                    name = sample_type.name
                    sample_type.delete()
                    messages.success(request, f"Sample type '{name}' deleted successfully.")
                elif option_type == 'provider':
                    provider = get_object_or_404(Provider, id=option_id)
                    name = provider.name
                    provider.delete()
                    messages.success(request, f"Provider '{name}' deleted successfully.")
                elif option_type == 'extractor':
                    extractor = get_object_or_404(Extractor, id=option_id)
                    name = extractor.name
                    extractor.delete()
                    messages.success(request, f"Extractor '{name}' deleted successfully.")
                elif option_type == 'cycler':
                    cycler = get_object_or_404(Cycler, id=option_id)
                    name = cycler.name
                    cycler.delete()
                    messages.success(request, f"Cycler '{name}' deleted successfully.")
                elif option_type == 'pcr_kit':
                    kit = get_object_or_404(PCRKit, id=option_id)
                    name = kit.name
                    kit.delete()
                    messages.success(request, f"PCR Kit '{name}' deleted successfully.")
                elif option_type == 'storage_place':
                    storage_place = get_object_or_404(StoragePlace, id=item_id)

                    # Check if the storage place contains samples
                    if hasattr(storage_place, 'pcrsample_set') and storage_place.pcrsample_set.exists():
                        messages.error(request, f"Cannot delete {storage_place.name} because it contains samples.")
                    else:
                        # Count child storage places for the message
                        child_count = StoragePlace.objects.filter(parent=storage_place).count()

                        # Get the type name for better messaging
                        type_name = storage_place.get_type_display()
                        name = storage_place.name

                        # Delete the storage place and all its children (CASCADE will handle this)
                        storage_place.delete()

                        if child_count > 0:
                            messages.success(request,
                                             f"{type_name} '{name}' and its {child_count} child storage location(s) deleted successfully.")
                        else:
                            messages.success(request, f"{type_name} '{name}' deleted successfully.")
            except Exception as e:
                messages.error(request,
                               f"Cannot delete this {option_type} because it is being used by samples: {str(e)}")

        # Redirect to maintain the section after form submission
        return redirect(f'/settings/?section={section}')

    # GET request - prepare context based on section
    context = {
        'section': section,
        'providers': Provider.objects.all(),
        'targets': Target.objects.all(),
        'sample_types': SampleType.objects.all(),
        'storage_places': StoragePlace.objects.all(),
        'extractors': Extractor.objects.all(),
        'cyclers': Cycler.objects.all(),
        'mikrogen_kits': PCRKit.objects.filter(type='mikrogen'),
        'external_kits': PCRKit.objects.filter(type='external'),
        'pcr_kits': PCRKit.objects.all().order_by('type', 'name'),
        # Added specific section data for storage places
        'rooms': StoragePlace.objects.filter(type='room', parent=None).order_by('name'),
        'storage_types': StoragePlace.STORAGE_TYPES,
    }

    # When storage places section is selected, build the hierarchy
    if section == 'storage_places':
        rooms = StoragePlace.objects.filter(type='room', parent=None).order_by('name')
        storage_hierarchy = []

        for room in rooms:
            room_item = {
                'id': room.id,
                'name': room.name,
                'type': room.type,
                'freezers': []
            }

            freezers = StoragePlace.objects.filter(type='freezer', parent=room)
            for freezer in freezers:
                freezer_item = {
                    'id': freezer.id,
                    'name': freezer.name,
                    'type': freezer.type,
                    'drawers': []
                }

                drawers = StoragePlace.objects.filter(type='drawer', parent=freezer)
                for drawer in drawers:
                    drawer_item = {
                        'id': drawer.id,
                        'name': drawer.name,
                        'type': drawer.type,
                        'boxes': []
                    }

                    boxes = StoragePlace.objects.filter(type='box', parent=drawer)
                    for box in boxes:
                        drawer_item['boxes'].append({
                            'id': box.id,
                            'name': box.name,
                            'type': box.type
                        })

                    freezer_item['drawers'].append(drawer_item)

                room_item['freezers'].append(freezer_item)

            storage_hierarchy.append(room_item)

        context['storage_hierarchy'] = storage_hierarchy

    return render(request, 'core/settings.html', context)

@login_required
def delete_option(request):
    """Delete a dropdown option"""
    if request.method == 'POST':
        option_type = request.POST.get('option_type')
        option_id = request.POST.get('option_id')

        try:
            if option_type == 'provider':
                Provider.objects.get(id=option_id).delete()
                messages.success(request, "Provider deleted successfully.")
            elif option_type == 'target':
                Target.objects.get(id=option_id).delete()
                messages.success(request, "Target deleted successfully.")
            elif option_type == 'sample_type':
                SampleType.objects.get(id=option_id).delete()
                messages.success(request, "Sample type deleted successfully.")
            elif option_type == 'storage_place':
                StoragePlace.objects.get(id=option_id).delete()
                messages.success(request, "Storage place deleted successfully.")
            elif option_type == 'extractor':
                Extractor.objects.get(id=option_id).delete()
                messages.success(request, "Extractor deleted successfully.")
            elif option_type == 'cycler':
                Cycler.objects.get(id=option_id).delete()
                messages.success(request, "Cycler deleted successfully.")
            elif option_type == 'pcr_kit':
                PCRKit.objects.get(id=option_id).delete()
                messages.success(request, "PCR kit deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting option: {str(e)}")

        return redirect('core:settings')

    return redirect('core:settings')


@login_required
def mark_in_use(request):
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        for sample_id in sample_ids:
            sample = get_object_or_404(PCRSample, id=sample_id)
            # Mark as active_use=True (not just in_use)
            sample.in_use = True
            sample.active_use = True  # Add this field to your model
            sample.current_user = request.user
            sample.not_found = False
            sample.save()

        messages.success(request, f"{len(sample_ids)} samples marked as in use.")
        return redirect('core:exported_list')

    return redirect('core:exported_list')

@login_required
def mark_samples_finished(request):
    """Mark selected samples as finished using"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        volume_used = request.POST.get('volume_used', 0)

        try:
            volume_used = float(volume_used)
        except ValueError:
            volume_used = 0

        for sample_id in sample_ids:
            sample = get_object_or_404(PCRSample, id=sample_id)
            if sample.in_use and sample.current_user == request.user:
                # Update the latest usage log
                usage_log = sample.usage_logs.filter(user=request.user, return_date__isnull=True).first()
                if usage_log:
                    usage_log.volume_used = volume_used
                    usage_log.return_date = datetime.now()
                    usage_log.save()

                # Mark sample as finished
                sample.mark_finished(volume_used)

        messages.success(request, f"{len(sample_ids)} samples marked as finished.")
        return redirect('core:inventory')

    return redirect('core:inventory')


@login_required
def record_active_use(request):
    """Change status from Reserved to In Use for selected samples"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        for sample_id in sample_ids:
            sample = get_object_or_404(PCRSample, id=sample_id)
            if sample.in_use and sample.current_user == request.user:
                # Change the status to "In Use" by adding a flag
                sample.active_use = True
                sample.save()

                # Instead of update_or_create, get the latest log entry
                usage_log = UsageLog.objects.filter(
                    sample=sample,
                    user=request.user,
                    return_date__isnull=True
                ).order_by('-checkout_date').first()

                if usage_log:
                    usage_log.active_use_date = datetime.now()
                    usage_log.save()
                else:
                    # Create a new log if none exists
                    UsageLog.objects.create(
                        sample=sample,
                        user=request.user,
                        active_use_date=datetime.now()
                    )

        messages.success(request, f"{len(sample_ids)} samples marked as in use.")
        return redirect('core:exported_list')

    return redirect('core:exported_list')

@login_required
def mark_samples_available(request):
    """Mark selected samples as available"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        for sample_id in sample_ids:
            sample = get_object_or_404(PCRSample, id=sample_id)
            # Reset all status flags
            sample.in_use = False
            sample.active_use = False
            sample.current_user = None
            sample.not_found = False
            sample.save()

        sample_text = "sample" if len(sample_ids) == 1 else "samples"
        messages.success(request, f"{len(sample_ids)} {sample_text} made available.")

    return redirect('core:inventory')

@login_required
def mark_in_use(request):
    """Mark selected samples as in use"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        for sample_id in sample_ids:
            sample = get_object_or_404(PCRSample, id=sample_id)
            sample.in_use = True
            sample.current_user = request.user
            sample.not_found = False  # Reset not found status if it was set
            sample.save()

            # Create usage log if doesn't exist
            if not UsageLog.objects.filter(sample=sample, user=request.user, return_date__isnull=True).exists():
                UsageLog.objects.create(
                    sample=sample,
                    user=request.user
                )

        messages.success(request, f"{len(sample_ids)} samples marked as in use.")
        return redirect('core:exported_list')

    return redirect('core:exported_list')


@login_required
def mark_samples_finished(request):
    """Mark samples as finished and deduct volume"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        volume_used = request.POST.get('volume_used', 0)

        try:
            volume_used = float(volume_used)
        except ValueError:
            volume_used = 0

        for sample_id in sample_ids:
            sample = get_object_or_404(PCRSample, id=sample_id)
            if sample.in_use and sample.current_user == request.user:
                # Update the latest usage log
                usage_log = UsageLog.objects.filter(sample=sample, user=request.user, return_date__isnull=True).first()
                if usage_log:
                    usage_log.volume_used = volume_used
                    usage_log.return_date = datetime.now()
                    usage_log.save()

                # Deduct volume and release the sample
                sample.sample_volume_remaining = max(0, sample.sample_volume_remaining - volume_used)
                sample.in_use = False
                sample.active_use = False
                sample.current_user = None
                sample.not_found = False
                sample.save()

        messages.success(request, f"{len(sample_ids)} samples processed with {volume_used} ml used.")
        return redirect('core:exported_list')

    return redirect('core:exported_list')


@login_required
def mark_samples_not_found(request):
    """Mark selected samples as not found - releases them"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        print(f"Received sample IDs: {sample_ids}")  # Add this debug line
        count = 0
        for sample_id in sample_ids:
            try:
                sample = get_object_or_404(PCRSample, id=sample_id)
                if sample.in_use and sample.current_user == request.user:
                    # Mark as not found
                    sample.not_found = True
                    sample.in_use = False
                    sample.current_user = None
                    sample.save()
                    count += 1

                    # Update usage log
                    UsageLog.objects.filter(
                        sample=sample,
                        user=request.user,
                        return_date__isnull=True
                    ).update(
                        not_found=True,
                        return_date=datetime.now()
                    )
            except Exception as e:
                print(f"Error processing sample {sample_id}: {str(e)}")

        messages.success(request, f"{count} samples marked as not found.")
        return redirect('core:exported_list')

    return redirect('core:exported_list')


@login_required
def refresh_samples(request):
    """Refresh samples - remove from list if no longer in use"""
    # Get all reserved samples for this user that are not actively in use
    samples_to_refresh = PCRSample.objects.filter(
        current_user=request.user,
        in_use=True,
        active_use=False,  # Only refresh samples that aren't actively in use
        not_found=True    # And aren't marked as not found
    )

    count = 0
    # Release any that are just reserved but not actively in use
    for sample in samples_to_refresh:
        sample.in_use = False
        sample.current_user = None
        sample.save()
        count += 1

    messages.success(request, f"{count} samples refreshed and returned to Available status.")
    return redirect('core:exported_list')

@login_required
def export_samples(request):
    """Export selected samples to CSV"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')

        # Debug to check if IDs are being received
        print(f"Received sample_ids: {sample_ids}")

        if not sample_ids:
            messages.error(request, "No samples were selected for export.")
            return redirect('core:inventory')

        samples = PCRSample.objects.filter(id__in=sample_ids)

        if not samples.exists():
            messages.error(request, "Selected samples not found.")
            return redirect('core:inventory')

        # Mark samples as in use
        for sample in samples:
            if not sample.in_use:
                sample.mark_in_use(request.user)
                UsageLog.objects.create(
                    sample=sample,
                    user=request.user
                )

        # Create Excel response
        current_date = datetime.now().strftime("%Y%m%d")
        filename = f"PCR_Datenbank_{current_date}.xlsx"

        response = HttpResponse(content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # Use pandas to create Excel file
        import pandas as pd
        from io import BytesIO

        data = []
        for sample in samples:
            data.append({
                'Mikrogen Internal Number': sample.mikrogen_internal_number,
                'Provider Number': sample.provider_number or '',
                'Provider': sample.provider.name,
                'Target': sample.target.name,
                'Positive For': sample.positive_for or '',
                'Negative For': sample.negative_for or '',
                'Sample Type': sample.sample_type.name,
                'Storage Place': sample.storage_place.name if sample.storage_place else '',
                'Date of Draw': sample.date_of_draw if sample.date_of_draw else '',
                'Age': sample.age if sample.age is not None else '',
                'Gender': sample.get_gender_display() if sample.gender else '',
                'Country of Origin': sample.country_of_origin or '',
                'Extraction Date': sample.extraction_date if sample.extraction_date else '',
                'Extractor': sample.extractor.name if sample.extractor else '',
                'Cycler': sample.cycler.name if sample.cycler else '',
                'PCR Kit (Mikrogen)': sample.mikrogen_pcr_kit.name if sample.mikrogen_pcr_kit else '',
                'PCR Kit (External)': sample.external_pcr_kit.name if sample.external_pcr_kit else '',
                'CT Value (Mikrogen)': sample.mikrogen_ct_value if sample.mikrogen_ct_value is not None else '',
                'CT Value (External)': sample.external_ct_value if sample.external_ct_value is not None else '',
                'Sample Volume': sample.sample_volume,
                'Sample Volume Remaining': sample.sample_volume_remaining,
                'Notes': sample.notes or ''
            })

        df = pd.DataFrame(data)

        # Write to Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)

        output.seek(0)
        response.write(output.getvalue())

        return response

    return redirect('core:inventory')

@login_required
def check_export_message(request):
    message = request.session.pop('export_message', None)
    return JsonResponse({'message': message})

@login_required
def import_samples(request):
    """Import samples from Excel file"""
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']

        # Check if file is an Excel file
        if not excel_file.name.endswith(('.xls', '.xlsx')):
            messages.error(request, "Uploaded file is not an Excel file.")
            return redirect('core:import')

        # Store the file temporarily if we need to process it again
        if 'excel_file' in request.FILES:
            temp_file = request.FILES['excel_file']
            fs = FileSystemStorage(location='/tmp')
            filename = fs.save(f"excel_import_{request.user.id}.xlsx", temp_file)
            temp_file_path = fs.path(filename)
        else:
            temp_file_path = request.POST.get('temp_file_path')

        # Process the Excel file
        try:
            # Read the Excel file
            df = pd.read_excel(temp_file_path if 'temp_file_path' in request.POST else excel_file)

            missing_columns = [col for col in
                               ['Mikrogen Internal Number', 'Provider', 'Target', 'Sample Type', 'Sample Volume']
                               if col not in df.columns]

            if missing_columns:
                messages.error(request, f"Missing required columns: {', '.join(missing_columns)}")
                return redirect('core:import')

            # Check for new targets before proceeding
            if 'confirm_targets' not in request.POST:
                # Collect all targets from Excel
                excel_targets = set()

                # From Target column
                if 'Target' in df.columns:
                    excel_targets.update(df['Target'].dropna().unique())

                # From Positive For column
                if 'Positive For' in df.columns:
                    for value in df['Positive For'].dropna():
                        if isinstance(value, str):
                            excel_targets.update([t.strip() for t in value.split(',')])

                # From Negative For column
                if 'Negative For' in df.columns:
                    for value in df['Negative For'].dropna():
                        if isinstance(value, str):
                            excel_targets.update([t.strip() for t in value.split(',')])

                # Check against existing targets
                existing_targets = set(Target.objects.values_list('name', flat=True))
                new_targets = excel_targets - existing_targets

                if new_targets:
                    return render(request, 'core/confirm_targets.html', {
                        'new_targets': sorted(new_targets),
                        'temp_file_path': temp_file_path
                    })

            # If user confirmed targets or no new targets needed
            if 'confirm_targets' in request.POST:
                if request.POST['confirm_targets'] == 'yes':
                    # Create new targets
                    new_targets = request.POST.getlist('new_targets')
                    for target_name in new_targets:
                        Target.objects.get_or_create(name=target_name)
                else:
                    # User canceled the import
                    messages.warning(request, "Import canceled - new targets were not added.")
                    return redirect('core:import')

            # Process rows
            samples_created = 0
            errors = []

            for idx, row in df.iterrows():
                try:
                    # Skip rows with empty required fields
                    if pd.isna(row['Mikrogen Internal Number']) or pd.isna(row['Sample Volume']):
                        errors.append(f"Row {idx + 2}: Missing required fields")
                        continue

                    # Check for duplicates before proceeding
                    mikrogen_number = str(row['Mikrogen Internal Number'])
                    if PCRSample.objects.filter(mikrogen_internal_number=mikrogen_number).exists():
                        errors.append(
                            f"Row {idx + 2}: Sample with Mikrogen Internal Number '{mikrogen_number}' already exists in the database.")
                        continue

                    # Get or create related objects
                    provider, _ = Provider.objects.get_or_create(name=row['Provider'])
                    target, _ = Target.objects.get_or_create(name=row['Target'])
                    sample_type, _ = SampleType.objects.get_or_create(name=row['Sample Type'])

                    # Create sample with required fields
                    sample = PCRSample(
                        mikrogen_internal_number=str(row['Mikrogen Internal Number']),
                        provider=provider,
                        target=target,
                        sample_type=sample_type,
                        sample_volume=float(row['Sample Volume']),
                        sample_volume_remaining=float(row['Sample Volume']),
                        added_by=request.user
                    )

                    # Handle optional fields
                    optional_fields = {
                        'Positive For': 'positive_for',
                        'Negative For': 'negative_for',
                        'Storage Place': 'storage_place',
                        'Date of Draw': 'date_of_draw',
                        'Age': 'age',
                        'Gender': 'gender',
                        'Country of Origin': 'country_of_origin',
                        'Extraction Date': 'extraction_date',
                        'Extractor': 'extractor',
                        'Cycler': 'cycler',
                        'Notes': 'notes'
                    }

                    for excel_field, model_field in optional_fields.items():
                        if excel_field in df.columns and not pd.isna(row[excel_field]):
                            value = row[excel_field]

                            # Handle specific field types
                            if excel_field == 'Storage Place':
                                storage_place, _ = StoragePlace.objects.get_or_create(name=value)
                                sample.storage_place = storage_place
                            elif excel_field == 'Extractor':
                                extractor, _ = Extractor.objects.get_or_create(name=value)
                                sample.extractor = extractor
                            elif excel_field == 'Cycler':
                                cycler, _ = Cycler.objects.get_or_create(name=value)
                                sample.cycler = cycler
                            elif excel_field == 'PCR Kit (Mikrogen)':
                                kit, _ = PCRKit.objects.get_or_create(name=value, type='mikrogen')
                                sample.mikrogen_pcr_kit = kit
                            elif excel_field == 'PCR Kit (External)':
                                kit, _ = PCRKit.objects.get_or_create(name=value, type='external')
                                sample.external_pcr_kit = kit
                            elif excel_field == 'Gender':
                                # Normalize gender value
                                gender = value.lower()
                                if gender in ['m', 'male', 'männlich']:
                                    sample.gender = 'male'
                                elif gender in ['f', 'female', 'weiblich']:
                                    sample.gender = 'female'
                            else:
                                setattr(sample, model_field, value)

                    sample.save()
                    samples_created += 1

                except Exception as e:
                    errors.append(f"Error in row {idx + 2}: {str(e)}")

            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

            if errors:
                messages.warning(request, f"Imported {samples_created} samples with {len(errors)} errors.")
                for error in errors[:10]:  # Show only first 10 errors
                    messages.error(request, error)
                if len(errors) > 10:
                    messages.error(request, f"... and {len(errors) - 10} more errors.")
            else:
                messages.success(request, f"Successfully imported {samples_created} samples.")

            return redirect('core:inventory')


        except Exception as e:
            if "violates unique constraint" in str(e) and "mikrogen_internal_number" in str(e):

                import re

                match = re.search(r'\(mikrogen_internal_number\)=\(([^)]+)\)', str(e))

                number = match.group(1) if match else "unknown"

                errors.append(
                    f"Row {idx + 2}: Duplicate Mikrogen Internal Number '{number}'. This sample already exists in the database.")

            else:

                errors.append(f"Row {idx + 2}: {str(e)}")

    return render(request, 'core/import.html')


@login_required
def exported_list(request):
    # Get only samples currently in use by this user (distinct results)
    samples = PCRSample.objects.filter(
        current_user=request.user,
        in_use=True
    ).distinct().order_by('mikrogen_internal_number')

    # Add volume percentage calculation
    for sample in samples:
        if sample.sample_volume > 0:
            sample.volume_percentage = (sample.sample_volume_remaining / sample.sample_volume) * 100
        else:
            sample.volume_percentage = 0

    context = {
        'samples': samples,
        'count': samples.count()
    }

    return render(request, 'core/exported_list.html', context)

@login_required
def download_template(request):
    """Download Excel template for importing samples"""
    # Create DataFrame with column headers
    columns = [
        'Mikrogen Internal Number',
        'Provider Number',
        'Provider',
        'Target',
        'Positive For',
        'Negative For',
        'Sample Type',
        'Storage Place',
        'Date of Draw',
        'Age',
        'Gender',
        'Country of Origin',
        'Extraction Date',
        'Extractor',
        'Cycler',
        'PCR Kit (Mikrogen)',
        'PCR Kit (External)',
        'CT Value (Mikrogen)',
        'CT Value (External)',
        'Sample Volume',
        'Notes'
    ]

    df = pd.DataFrame(columns=columns)

    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    # Prepare response
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=pcr_samples_template.xlsx'

    return response
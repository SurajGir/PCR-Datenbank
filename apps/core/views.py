import json
import os
import re
import tempfile
from datetime import datetime
from typing import Union

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.db.models import Q, Count, F, ExpressionWrapper, FloatField
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

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

    # --- NEW: Get BOTH the count and the actual low volume samples ---
    low_volume_qs = PCRSample.objects.filter(sample_volume__gt=0).annotate(
        percentage=ExpressionWrapper(
            F('sample_volume_remaining') * 100.0 / F('sample_volume'),
            output_field=FloatField()
        )
    ).filter(percentage__lt=25).order_by('percentage') # Show the emptiest ones first

    low_volume_count = low_volume_qs.count()
    low_volume_list = low_volume_qs[:10] # Grab the top 10 for the table

    # --- NEW: Get "My Active Samples" ---
    my_active_samples = PCRSample.objects.filter(
        current_user=request.user,
        in_use=True
    ).order_by('mikrogen_internal_number')

    # Sample type distribution (Unchanged)
    sample_type_data = list(PCRSample.objects.values('sample_type__name')
                            .annotate(count=Count('id'))
                            .order_by('-count')[:10])
    sample_type_labels = json.dumps([item['sample_type__name'] for item in sample_type_data])
    sample_type_counts = [item['count'] for item in sample_type_data]

    # Target distribution (Unchanged)
    target_data = list(PCRSample.objects.values('target__name')
                       .annotate(count=Count('id'))
                       .order_by('-count')[:10])
    target_labels = json.dumps([item['target__name'] for item in target_data])
    target_counts = [item['count'] for item in target_data]

    # Recent activity (Unchanged)
    recent_logs = UsageLog.objects.select_related('sample', 'user').order_by('-checkout_date')[:10]
    for log in recent_logs:
        log.action_type = "returned" if log.return_date else "checked out"
        log.timestamp = log.return_date if log.return_date else log.checkout_date

    context = {
        'total_samples': total_samples,
        'in_use_count': in_use_count,
        'available_count': available_count,
        'low_volume_count': low_volume_count,
        'low_volume_list': low_volume_list,
        'my_active_samples': my_active_samples,
        'sample_type_labels': sample_type_labels,
        'sample_type_data': sample_type_counts,
        'target_labels': target_labels,
        'target_data': target_counts,
        'recent_logs': recent_logs,
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

    # --- NEW: Empty defaults for Volume inputs + get the unit ---
    min_volume = request.GET.get('min_volume', '')
    max_volume = request.GET.get('max_volume', '')
    filter_unit = request.GET.get('filter_unit', 'mL')

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

        if mikrogen_filter != Q():
            ct_filters |= mikrogen_filter

        # Handle External CT values
        external_filter = Q()
        if min_ct and min_ct != '0':
            external_filter &= Q(external_ct_value__gte=float(min_ct))
        if max_ct and max_ct != '50':
            external_filter &= Q(external_ct_value__lte=float(max_ct))

        if external_filter != Q():
            ct_filters |= external_filter

        if ct_filters != Q():
            samples = samples.filter(ct_filters)

    # --- NEW: Unit-Aware Volume Filters ---
    if min_volume or max_volume:
        try:
            # If left blank, min becomes 0 and max becomes infinity
            min_v = float(min_volume) if min_volume else 0.0
            max_v = float(max_volume) if max_volume else float('inf')

            if filter_unit == 'mL':
                samples = samples.filter(
                    Q(volume_unit='mL', sample_volume_remaining__gte=min_v, sample_volume_remaining__lte=max_v) |
                    Q(volume_unit='uL', sample_volume_remaining__gte=min_v * 1000,
                      sample_volume_remaining__lte=max_v * 1000) |
                    Q(volume_unit='L', sample_volume_remaining__gte=min_v / 1000,
                      sample_volume_remaining__lte=max_v / 1000)
                )
            elif filter_unit == 'uL':
                samples = samples.filter(
                    Q(volume_unit='uL', sample_volume_remaining__gte=min_v, sample_volume_remaining__lte=max_v) |
                    Q(volume_unit='mL', sample_volume_remaining__gte=min_v / 1000,
                      sample_volume_remaining__lte=max_v / 1000) |
                    Q(volume_unit='L', sample_volume_remaining__gte=min_v / 1000000,
                      sample_volume_remaining__lte=max_v / 1000000)
                )
            elif filter_unit == 'L':
                samples = samples.filter(
                    Q(volume_unit='L', sample_volume_remaining__gte=min_v, sample_volume_remaining__lte=max_v) |
                    Q(volume_unit='mL', sample_volume_remaining__gte=min_v * 1000,
                      sample_volume_remaining__lte=max_v * 1000) |
                    Q(volume_unit='uL', sample_volume_remaining__gte=min_v * 1000000,
                      sample_volume_remaining__lte=max_v * 1000000)
                )
        except ValueError:
            pass  # Ignore if text was typed by accident

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
        f"CT={min_ct}-{max_ct}, volume={min_volume}-{max_volume} {filter_unit}")
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
            'filter_unit': filter_unit,  # --- NEW: Pass unit back to HTML form ---
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
    section = request.GET.get('section', 'storage')  # Add default section

    if request.method == 'POST':
        action = request.POST.get('action')
        option_type = request.POST.get('option_type')
        item_id = request.POST.get('item_id')

        # Make sure section is defined for the redirects
        section = request.GET.get('section', 'storage')

        # ---------------------------------------------------------
        # 1. ADD ACTION
        # ---------------------------------------------------------
        if action == 'add':
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

            return redirect(f'/settings/?section={section}')

        # ---------------------------------------------------------
        # 2. MOVE ACTION
        # ---------------------------------------------------------
        elif action == 'move':
            new_parent_id = request.POST.get('new_parent_id')
            item = get_object_or_404(StoragePlace, id=item_id)

            # Prevent circular references
            if new_parent_id:
                new_parent = get_object_or_404(StoragePlace, id=new_parent_id)

                current = new_parent
                while current:
                    if current.id == item.id:
                        messages.error(request, "Cannot move a storage location into its own descendant.")
                        return redirect(f'/settings/?section={section}')
                    current = current.parent

                # Check if the new parent is of the correct type
                if item.type == 'room':
                    messages.error(request,
                                   "Rooms cannot be placed inside other locations. They must be at the top level.")
                elif item.type == 'freezer' and new_parent.type != 'room':
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

            return redirect(f'/settings/?section={section}')

        # ---------------------------------------------------------
        # 3. DELETE ACTION (MERGED & FIXED)
        # ---------------------------------------------------------
        elif action == 'delete':
            option_id = request.POST.get('option_id')

            if not item_id and not option_id:
                messages.error(request, "No ID provided for deletion.")
                return redirect(f'/settings/?section={section}')

            try:
                # Delete Settings Options
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

                # Delete Storage Places (Fallback if no explicit option_type was sent)
                elif not option_type or option_type == 'storage_place':
                    target_id = item_id if item_id else option_id
                    storage_place = get_object_or_404(StoragePlace, id=target_id)

                    if PCRSample.objects.filter(storage_place=storage_place).exists():
                        messages.error(request, f"Cannot delete {storage_place.name} because it contains samples.")
                    elif StoragePlace.objects.filter(parent=storage_place).exists():
                        messages.error(request,
                                       f"Cannot delete {storage_place.name} because it contains other storage locations.")
                    else:
                        name = storage_place.name
                        storage_place.delete()
                        messages.success(request, f"{name} deleted successfully.")
            except Exception as e:
                error_target = option_type if option_type else "storage place"
                messages.error(request, f"Cannot delete {error_target}: {str(e)}")

            return redirect(f'/settings/?section={section}')

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
        volume_unit = request.POST.get('volume_unit', 'mL')

        # Create new sample with required fields
        sample = PCRSample(
            mikrogen_internal_number=mikrogen_internal_number,
            provider_id=provider_id,
            target_id=target_id,
            sample_type_id=sample_type_id,
            sample_volume=float(sample_volume),
            sample_volume_remaining=float(sample_volume),
            volume_unit=volume_unit,
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

        # Volume needs special handling to track history and unit changes
        new_volume = float(request.POST.get('sample_volume', 0))
        new_unit = request.POST.get('volume_unit', sample.volume_unit)  # Fallback to current unit

        # Case 1: The user changed the Unit (e.g., fixing a typo from mL to uL)
        if new_unit != sample.volume_unit:
            # Figure out what percentage of the sample is currently left
            if sample.sample_volume > 0:
                percentage_left = sample.sample_volume_remaining / sample.sample_volume
            else:
                percentage_left = 1.0

            # Update the sample with the new unit and volume
            sample.volume_unit = new_unit
            sample.sample_volume = new_volume
            # Apply that same percentage to the new volume
            sample.sample_volume_remaining = new_volume * percentage_left

        # Case 2: The user only changed the Number, unit stayed the same
        elif new_volume != sample.sample_volume:
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
    # Get the section from the URL parameter or POST data
    section = request.GET.get('section', request.POST.get('section', 'targets'))

    if request.method == 'POST':
        action = request.POST.get('action')
        option_type = request.POST.get('option_type')
        item_id = request.POST.get('item_id')
        option_id = request.POST.get('option_id')

        # --------------------------------------------------------
        # 1. DELETE LOGIC
        # --------------------------------------------------------
        if action == 'delete':
            try:
                if not (item_id or option_id):
                    messages.error(request, "No ID provided for deletion.")
                    return redirect(f"{reverse('core:settings')}?section={section}")

                delete_id = option_id if option_id else item_id
                success_message = None

                if option_type == 'target':
                    item = get_object_or_404(Target, id=delete_id)
                    if PCRSample.objects.filter(target=item).exists():
                        messages.error(request, f"Cannot delete '{item.name}': it is linked to existing samples.")
                    else:
                        name = item.name
                        item.delete()
                        success_message = f"Target '{name}' deleted successfully."

                elif option_type == 'sample_type':
                    item = get_object_or_404(SampleType, id=delete_id)
                    if PCRSample.objects.filter(sample_type=item).exists():
                        messages.error(request, f"Cannot delete '{item.name}': it is linked to existing samples.")
                    else:
                        name = item.name
                        item.delete()
                        success_message = f"Sample type '{name}' deleted successfully."

                elif option_type == 'provider':
                    item = get_object_or_404(Provider, id=delete_id)
                    if PCRSample.objects.filter(provider=item).exists():
                        messages.error(request, f"Cannot delete '{item.name}': it is linked to existing samples.")
                    else:
                        name = item.name
                        item.delete()
                        success_message = f"Provider '{name}' deleted successfully."

                elif option_type == 'extractor':
                    item = get_object_or_404(Extractor, id=delete_id)
                    if PCRSample.objects.filter(extractor=item).exists():
                        messages.error(request, f"Cannot delete '{item.name}': it is linked to existing samples.")
                    else:
                        name = item.name
                        item.delete()
                        success_message = f"Extractor '{name}' deleted successfully."

                elif option_type == 'cycler':
                    item = get_object_or_404(Cycler, id=delete_id)
                    if PCRSample.objects.filter(cycler=item).exists():
                        messages.error(request, f"Cannot delete '{item.name}': it is linked to existing samples.")
                    else:
                        name = item.name
                        item.delete()
                        success_message = f"Cycler '{name}' deleted successfully."

                elif option_type == 'pcr_kit':
                    item = get_object_or_404(PCRKit, id=delete_id)
                    if PCRSample.objects.filter(mikrogen_pcr_kit=item).exists() or PCRSample.objects.filter(
                            external_pcr_kit=item).exists():
                        messages.error(request, f"Cannot delete '{item.name}': it is used in sample records.")
                    else:
                        name = item.name
                        item.delete()
                        success_message = f"PCR Kit '{name}' deleted successfully."

                elif option_type == 'storage_place':
                    item = get_object_or_404(StoragePlace, id=delete_id)

                    # 1. Gather this item and ALL its nested children (Freezers, Drawers, Boxes)
                    def get_all_storage_ids(place):
                        ids = [place.id]
                        for child in StoragePlace.objects.filter(parent=place):
                            ids.extend(get_all_storage_ids(child))
                        return ids

                    all_ids = get_all_storage_ids(item)

                    # 2. Check if ANY of these locations currently hold a physical sample
                    if PCRSample.objects.filter(storage_place_id__in=all_ids).exists():
                        messages.error(request,
                                       f"Cannot delete '{item.name}': It (or a sub-location inside it) currently contains samples. Please move the samples first.")
                    else:
                        name = item.name
                        # 3. Safely delete the entire tree at once
                        StoragePlace.objects.filter(id__in=all_ids).delete()
                        success_message = f"'{name}' and all its empty sub-locations were deleted successfully."

                if success_message:
                    messages.success(request, success_message)

            except Exception as e:
                messages.error(request, f"An unexpected error occurred during deletion: {str(e)}")

        # --------------------------------------------------------
        # 2. ADD LOGIC
        # --------------------------------------------------------
        elif action == 'add':
            name = request.POST.get('name')

            if not name or name.strip() == '':
                messages.error(request, f"Please enter a valid name for the new {option_type.replace('_', ' ')}.")
            else:
                try:
                    if option_type == 'target':
                        Target.objects.create(name=name)
                    elif option_type == 'sample_type':
                        SampleType.objects.create(name=name)
                    elif option_type == 'provider':
                        Provider.objects.create(name=name)
                    elif option_type == 'extractor':
                        Extractor.objects.create(name=name)
                    elif option_type == 'cycler':
                        Cycler.objects.create(name=name)
                    elif option_type == 'pcr_kit':
                        kit_type = request.POST.get('kit_type', 'external')
                        PCRKit.objects.create(name=name, type=kit_type)
                    elif option_type == 'storage_place':
                        storage_type = request.POST.get('type')  # Ensure this matches your form input name
                        parent_id = request.POST.get('parent_id')
                        parent_obj = StoragePlace.objects.get(id=parent_id) if parent_id else None
                        StoragePlace.objects.create(name=name, type=storage_type, parent=parent_obj)

                    messages.success(request, f"Successfully added '{name}'!")
                except Exception as e:
                    messages.error(request, f"Error adding new item: {str(e)}")

        # --------------------------------------------------------
        # 3. EDIT LOGIC
        # --------------------------------------------------------
        elif action == 'edit':
            new_name = request.POST.get('name')

            if not option_id or not new_name or new_name.strip() == '':
                messages.error(request, "Invalid data provided for editing.")
            else:
                try:
                    if option_type == 'target':
                        item = get_object_or_404(Target, id=option_id)
                        item.name = new_name
                        item.save()
                    elif option_type == 'sample_type':
                        item = get_object_or_404(SampleType, id=option_id)
                        item.name = new_name
                        item.save()
                    elif option_type == 'provider':
                        item = get_object_or_404(Provider, id=option_id)
                        item.name = new_name
                        item.save()
                    elif option_type == 'extractor':
                        item = get_object_or_404(Extractor, id=option_id)
                        item.name = new_name
                        item.save()
                    elif option_type == 'cycler':
                        item = get_object_or_404(Cycler, id=option_id)
                        item.name = new_name
                        item.save()
                    elif option_type == 'pcr_kit':
                        item = get_object_or_404(PCRKit, id=option_id)
                        item.name = new_name
                        kit_type = request.POST.get('kit_type')
                        if kit_type:
                            item.type = kit_type
                        item.save()
                    elif option_type == 'storage_place':
                        item = get_object_or_404(StoragePlace, id=option_id)
                        item.name = new_name
                        storage_type = request.POST.get('storage_type')
                        if storage_type:
                            item.type = storage_type
                        parent_id = request.POST.get('parent_id')
                        if parent_id:
                            item.parent = StoragePlace.objects.get(id=parent_id)
                        item.save()

                    messages.success(request, f"Successfully updated to '{new_name}'!")
                except Exception as e:
                    messages.error(request, f"Error updating item: {str(e)}")

        # --------------------------------------------------------
        # 4. MOVE LOGIC (For Storage Places)
        # --------------------------------------------------------
        elif action == 'move':
            new_parent_id = request.POST.get('new_parent_id')

            if option_type == 'storage_place' and item_id:
                try:
                    item = get_object_or_404(StoragePlace, id=item_id)

                    if new_parent_id:
                        new_parent = get_object_or_404(StoragePlace, id=new_parent_id)
                        item.parent = new_parent
                    else:
                        item.parent = None  # Moved to top level (Room)

                    item.save()
                    messages.success(request, f"Successfully moved '{item.name}'.")
                except Exception as e:
                    messages.error(request, f"Error moving location: {str(e)}")

        # --------------------------------------------------------
        # REDIRECT AT THE END OF THE POST BLOCK
        # --------------------------------------------------------
        return redirect(f"{reverse('core:settings')}?section={section}")
    # --------------------------------------------------------
    # CONTEXT PREPARATION (GET REQUEST)
    # --------------------------------------------------------
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
    """Mark samples as finished and deduct volume unit-safely"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        volume_used_str = request.POST.get('volume_used', 0)
        deduction_unit = request.POST.get('deduction_unit', 'mL')  # Grab the dropdown value

        try:
            volume_used = float(volume_used_str)
        except ValueError:
            volume_used = 0

        for sample_id in sample_ids:
            sample = get_object_or_404(PCRSample, id=sample_id)
            if sample.in_use and sample.current_user == request.user:

                # --- UNIT CONVERSION MATH ---
                # Convert the "used volume" into the sample's native unit
                converted_volume_used = volume_used

                if deduction_unit != sample.volume_unit:
                    if deduction_unit == 'mL' and sample.volume_unit == 'uL':
                        converted_volume_used = volume_used * 1000
                    elif deduction_unit == 'mL' and sample.volume_unit == 'L':
                        converted_volume_used = volume_used / 1000
                    elif deduction_unit == 'uL' and sample.volume_unit == 'mL':
                        converted_volume_used = volume_used / 1000
                    elif deduction_unit == 'uL' and sample.volume_unit == 'L':
                        converted_volume_used = volume_used / 1000000
                    elif deduction_unit == 'L' and sample.volume_unit == 'mL':
                        converted_volume_used = volume_used * 1000
                    elif deduction_unit == 'L' and sample.volume_unit == 'uL':
                        converted_volume_used = volume_used * 1000000

                # Update the latest usage log
                usage_log = UsageLog.objects.filter(sample=sample, user=request.user, return_date__isnull=True).first()
                if usage_log:
                    # Save the explicit unit in the log so the dashboard knows what was used
                    usage_log.volume_used = volume_used
                    usage_log.volume_unit = deduction_unit
                    usage_log.return_date = datetime.now()
                    usage_log.save()

                # Deduct volume using the converted math and release the sample
                sample.sample_volume_remaining = max(0, sample.sample_volume_remaining - converted_volume_used)
                sample.in_use = False
                sample.active_use = False
                sample.current_user = None
                sample.not_found = False
                sample.save()

        messages.success(request, f"{len(sample_ids)} samples processed. Deducted {volume_used} {deduction_unit}.")
        return redirect('core:exported_list')

    return redirect('core:exported_list')


@login_required
def record_active_use(request):
    """Change status to In Use (Active) - Works for Reserved or Not Found samples"""
    if request.method == 'POST':
        # 1. Get IDs and force them to be unique to avoid double-counting
        sample_ids = list(set(request.POST.getlist('sample_ids')))

        # 2. Update the samples in one single database hit
        # This returns the ACTUAL number of rows changed in the DB
        actual_count = PCRSample.objects.filter(
            id__in=sample_ids,
            current_user=request.user
        ).update(
            active_use=True,
            in_use=True,
            not_found=False
        )

        # 3. Handle the logs for these specific samples
        for s_id in sample_ids:
            # We update the log if it exists, or create if missing
            log_updated = UsageLog.objects.filter(
                sample_id=s_id,
                user=request.user,
                return_date__isnull=True
            ).update(
                active_use_date=datetime.now(),
                not_found=False
            )

            if not log_updated:
                UsageLog.objects.create(
                    sample_id=s_id,
                    user=request.user,
                    active_use_date=datetime.now()
                )

        messages.success(request, f"{actual_count} samples are now actively In Use.")

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

            # --- NEW: Close any open logs for this sample ---
            UsageLog.objects.filter(
                sample=sample,
                return_date__isnull=True
            ).update(
                return_date=datetime.now(),
                notes="Marked available (Forced release)"
            )

        sample_text = "sample" if len(sample_ids) == 1 else "samples"
        messages.success(request, f"{len(sample_ids)} {sample_text} made available.")

    return redirect('core:inventory')

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

def safe_convert_value(value: str, to_type: str = 'float') -> Union[float, int, str]:
    """Safely convert a value to a numeric type or return original if not convertible"""
    if not isinstance(value, str):
        return value
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return value


@login_required
def export_samples(request):
    """Export selected samples to Excel with the new 4-column storage format"""
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')

        if not sample_ids:
            messages.error(request, "No samples were selected for export.")
            return redirect('core:inventory')

        samples = PCRSample.objects.filter(id__in=sample_ids)
        if not samples.exists():
            messages.error(request, "Selected samples not found.")
            return redirect('core:inventory')

        # Prepare data for export
        export_data = []
        for sample in samples:
            if not sample.in_use:
                sample.in_use = True
                sample.current_user = request.user
                sample.save()
                UsageLog.objects.create(
                    sample=sample,
                    user=request.user
                )

            # --- NEW LOGIC: EXTRACT HIERARCHY FOR EXPORT ---
            room, freezer, drawer, box = '', '', '', ''
            sp = sample.storage_place

            # We work backwards from the saved location up to the Room
            if sp:
                # This logic assumes: Box -> Drawer -> Freezer -> Room
                # It safely checks if a parent exists at each step
                curr = sp
                path = []
                while curr is not None:
                    path.insert(0, curr.name)
                    curr = curr.parent

                # Assign based on depth found (Room is top, Box is bottom)
                if len(path) >= 1: room = path[0]
                if len(path) >= 2: freezer = path[1]
                if len(path) >= 3: drawer = path[2]
                if len(path) >= 4: box = path[3]
            # ----------------------------------------------

            # Add sample data to export list
            export_data.append({
                'Mikrogen Internal Number': sample.mikrogen_internal_number,
                'Provider Number': sample.provider_number or '',
                'Provider': sample.provider.name if sample.provider else '',
                'Target': sample.target.name if sample.target else '',
                'Positive For': sample.positive_for or '',
                'Negative For': sample.negative_for or '',
                'Sample Type': sample.sample_type.name if sample.sample_type else '',

                # --- MATCHING THE NEW 4-COLUMN FORMAT ---
                'Storage: Room': room,
                'Storage: Freezer': freezer,
                'Storage: Drawer': drawer,
                'Storage: Box': box,
                # ----------------------------------------

                'Date of Draw': sample.date_of_draw.strftime('%Y-%m-%d') if sample.date_of_draw else '',
                'Age': str(sample.age) if sample.age is not None else '',
                'Gender': sample.get_gender_display() if sample.gender else '',
                'Country of Origin': sample.country_of_origin or '',
                'Extraction Date': sample.extraction_date.strftime('%Y-%m-%d') if sample.extraction_date else '',
                'Extractor': sample.extractor.name if sample.extractor else '',
                'Cycler': sample.cycler.name if sample.cycler else '',
                'PCR Kit (Mikrogen)': sample.mikrogen_pcr_kit.name if sample.mikrogen_pcr_kit else '',
                'PCR Kit (External)': sample.external_pcr_kit.name if sample.external_pcr_kit else '',
                'CT Value (Mikrogen)': str(sample.mikrogen_ct_value) if sample.mikrogen_ct_value is not None else '',
                'CT Value (External)': str(sample.external_ct_value) if sample.external_ct_value is not None else '',
                'Sample Volume': f"{sample.sample_volume} {sample.volume_unit}",
                'Sample Volume Remaining': f"{sample.sample_volume_remaining} {sample.volume_unit}",
                'Notes': sample.notes or ''
            })

        # Create Excel file
        current_date = datetime.now().strftime("%Y%m%d")
        filename = f"PCR_Datenbank_{current_date}.xlsx"
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        df = pd.DataFrame(export_data)

        try:
            with pd.ExcelWriter(temp_path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)

            with open(temp_path, 'rb') as f:
                response = HttpResponse(
                    f.read(),
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = f'attachment; filename="{filename}"'

            os.remove(temp_path)
            return response

        except Exception as e:
            messages.error(request, f"Error creating Excel file: {str(e)}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return redirect('core:inventory')

    return redirect('core:inventory')

@login_required
@require_POST
def release_from_export(request):
    """
    Removes samples from the user's private export list.
    Preserves the 'Not Found' status so it remains visible on the main inventory.
    """
    sample_ids = request.POST.getlist('sample_ids')
    samples = PCRSample.objects.filter(id__in=sample_ids)

    for sample in samples:
        sample.current_user = None
        sample.in_use = False
        sample.active_use = False
        # IMPORTANT: We do NOT set sample.not_found = False here.
        # If it was Red (Not Found), it stays Red on the main page.
        sample.save()

    UsageLog.objects.filter(
        sample__in=samples,
        user=request.user,
        return_date__isnull=True
    ).update(
        return_date=datetime.now(),
        notes="Released without using volume"
    )

    messages.success(request, f"{samples.count()} samples released to the main inventory.")
    return redirect('core:exported_list')


@login_required
def download_template(request):
    """Download Excel template for importing samples"""
    # Create DataFrame with the updated 4-column storage headers
    columns = [
        'Mikrogen Internal Number',
        'Provider Number',
        'Provider',
        'Target',
        'Positive For',
        'Negative For',
        'Sample Type',

        # --- NEW STORAGE COLUMNS ---
        'Storage: Room',
        'Storage: Freezer',
        'Storage: Drawer',
        'Storage: Box',
        # ---------------------------

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

    # Create Excel file using a temporary file
    filename = "pcr_samples_template.xlsx"
    temp_path = os.path.join(tempfile.gettempdir(), filename)

    try:
        with pd.ExcelWriter(temp_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)

        # Read the file and create response
        with open(temp_path, 'rb') as f:
            response = HttpResponse(
                f.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # Clean up
        os.remove(temp_path)
        return response

    except Exception as e:
        messages.error(request, f"Error creating template: {str(e)}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return redirect('core:inventory')


@login_required
def import_samples(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']

        if not excel_file.name.endswith(('.xls', '.xlsx')):
            messages.error(request, "Uploaded file is not an Excel file.")
            return redirect('core:import')

        errors = []
        samples_created = 0

        try:
            # Read the file directly from memory (Fixes the Render Cloud bug!)
            df = pd.read_excel(excel_file)

            # Check Mandatory Columns
            required_cols = [
                'Mikrogen Internal Number', 'Provider Number', 'Provider',
                'Target', 'Sample Type', 'Sample Volume'
            ]
            missing_columns = [col for col in required_cols if col not in df.columns]
            if missing_columns:
                messages.error(request, f"Missing required columns: {', '.join(missing_columns)}")
                return redirect('core:import')

            # ==========================================
            # YOUR CUSTOM LOGIC STARTS HERE
            # ==========================================
            for index, row in df.iterrows():
                current_row_idx = index + 2

                mikrogen_id = str(row.get('Mikrogen Internal Number', '')).strip()
                if mikrogen_id.lower() == 'nan' or not mikrogen_id:
                    errors.append(f"Row {current_row_idx}: ID is missing.")
                    continue
                if PCRSample.objects.filter(mikrogen_internal_number=mikrogen_id).exists():
                    errors.append(f"Row {current_row_idx}: ID '{mikrogen_id}' already exists.")
                    continue

                # Auto-Create approved settings
                provider, _ = Provider.objects.get_or_create(name=str(row.get('Provider', '')).strip())
                target, _ = Target.objects.get_or_create(name=str(row.get('Target', '')).strip())
                sample_type, _ = SampleType.objects.get_or_create(name=str(row.get('Sample Type', '')).strip())

                mk_kit, ex_kit = None, None
                mk_name = str(row.get('PCR Kit (Mikrogen)', '')).strip()
                if mk_name and mk_name.lower() != 'nan':
                    mk_kit, _ = PCRKit.objects.get_or_create(name=mk_name, type='mikrogen')

                ex_name = str(row.get('PCR Kit (External)', '')).strip()
                if ex_name and ex_name.lower() != 'nan':
                    ex_kit, _ = PCRKit.objects.get_or_create(name=ex_name, type='external')

                # Parse Volume (Your smart splitter)
                vol_raw = str(row.get('Sample Volume', '')).strip().lower()
                volume_unit = 'uL' if 'ul' in vol_raw or 'µl' in vol_raw else 'mL'
                try:
                    numeric_vol = float(re.sub(r'[^\d.]', '', vol_raw))
                except ValueError:
                    errors.append(f"Row {current_row_idx}: Invalid Volume format.")
                    continue

                # The 4-Column Storage Mapper
                storage_place = None
                room_name = str(row.get('Storage: Room', '')).strip()
                freezer_name = str(row.get('Storage: Freezer', '')).strip()
                drawer_name = str(row.get('Storage: Drawer', '')).strip()
                box_name = str(row.get('Storage: Box', '')).strip()

                room_name = room_name if room_name.lower() != 'nan' else ''
                freezer_name = freezer_name if freezer_name.lower() != 'nan' else ''
                drawer_name = drawer_name if drawer_name.lower() != 'nan' else ''
                box_name = box_name if box_name.lower() != 'nan' else ''

                if box_name:
                    storage_place = StoragePlace.objects.filter(
                        name=box_name, parent__name=drawer_name,
                        parent__parent__name=freezer_name, parent__parent__parent__name=room_name
                    ).first()
                    if not storage_place:
                        errors.append(f"Row {current_row_idx}: Exact box path not found.")
                        continue
                elif drawer_name:
                    storage_place = StoragePlace.objects.filter(
                        name=drawer_name, parent__name=freezer_name, parent__parent__name=room_name
                    ).first()
                elif freezer_name:
                    storage_place = StoragePlace.objects.filter(
                        name=freezer_name, parent__name=room_name
                    ).first()
                elif room_name:
                    storage_place = StoragePlace.objects.filter(name=room_name).first()
                    if not storage_place and room_name:
                        errors.append(f"Row {current_row_idx}: Room '{room_name}' not found.")
                        continue

                # Create Sample
                sample = PCRSample(
                    mikrogen_internal_number=mikrogen_id,
                    provider_number=str(row.get('Provider Number', '')).strip() if str(
                        row.get('Provider Number', '')).strip().lower() != 'nan' else None,
                    provider=provider,
                    target=target,
                    sample_type=sample_type,
                    mikrogen_pcr_kit=mk_kit,
                    external_pcr_kit=ex_kit,
                    storage_place=storage_place,
                    sample_volume=numeric_vol,
                    sample_volume_remaining=numeric_vol,
                    volume_unit=volume_unit,
                    added_by=request.user,
                    positive_for=row.get('Positive For') if pd.notna(row.get('Positive For')) else None,
                    negative_for=row.get('Negative For') if pd.notna(row.get('Negative For')) else None,
                    notes=row.get('Notes') if pd.notna(row.get('Notes')) else None,
                    country_of_origin=row.get('Country of Origin') if pd.notna(row.get('Country of Origin')) else None,
                )

                if pd.notna(row.get('Age')):
                    try:
                        sample.age = int(row.get('Age'))
                    except:
                        pass
                if pd.notna(row.get('CT Value (Mikrogen)')):
                    sample.mikrogen_ct_value = float(row.get('CT Value (Mikrogen)'))
                if pd.notna(row.get('CT Value (External)')):
                    sample.external_ct_value = float(row.get('CT Value (External)'))
                if pd.notna(row.get('Date of Draw')):
                    try:
                        sample.date_of_draw = pd.to_datetime(row.get('Date of Draw')).date()
                    except:
                        pass
                if pd.notna(row.get('Extraction Date')):
                    try:
                        sample.extraction_date = pd.to_datetime(row.get('Extraction Date')).date()
                    except:
                        pass

                sample.save()
                samples_created += 1

            if errors:
                request.session['import_errors'] = errors
                messages.warning(request,
                                 f"Imported {samples_created} samples with {len(errors)} errors. Check the logs.")
            else:
                messages.success(request, f"Successfully imported {samples_created} samples.")

            return redirect('core:inventory')

        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f"Import failed: {str(e)}")
            return redirect('core:import')

    return render(request, 'core/import.html')

@login_required
def get_import_errors(request):
    """AJAX endpoint to get import errors from session"""
    errors = request.session.get('import_errors', [])
    return JsonResponse({'errors': errors})

@login_required
def exported_list(request):
    """View for displaying list of exported/in-use samples assigned to the current user"""
    # FIX: Only show samples belonging to the logged-in user
    samples = PCRSample.objects.filter(
        current_user=request.user
    ).order_by('mikrogen_internal_number')

    # Add status information for each sample (Same as before)
    for sample in samples:
        if sample.not_found:
            sample.status = 'Not Found'
        elif sample.active_use:
            sample.status = 'In Use'
        else:
            sample.status = 'Reserved'

    context = {
        'samples': samples,
    }

    return render(request, 'core/exported_list.html', context)

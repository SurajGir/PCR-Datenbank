# apps/core/management/commands/add_initial_data.py
from django.core.management.base import BaseCommand
from apps.core.models import SampleType, Provider, Target, PCRKit, StoragePlace, Extractor, Cycler

class Command(BaseCommand):
    help = 'Adds initial data for dropdown options'

    def handle(self, *args, **options):
        # Add Sample Types
        sample_types = [
            # Add your specific sample types here
            "Stool",
            "Sputum",
            "BAL",
            "Tracheal secretion",
            "Swab",
            "Saliva",
            "Urine",
            "Culture",
            "Urogenital swab",
            "Plasma",
            "Serum",
            "Eluate: Stool",
            "Eluate: Sputum",
            "Eluate: BAL",
            "Eluate: Tracheal secretion",
            "Eluate: Swab",
            "Eluate: Saliva",
            "Eluate: Urine",
            "Eluate: Culture",
            "Eluate: Urogenital swab",
            "Eluate: Plasma",
            "Eluate: Serum",
        ]
        self.stdout.write('Adding Sample Types...')
        for name in sample_types:
            obj, created = SampleType.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f'  - Added: {name}')
            else:
                self.stdout.write(f'  - Already exists: {name}')

        # Add Providers
        providers = [
            # Add your specific providers here
            "AbBaltis",
            "BIOMEX GmbH",
            "Bioscientia Healthcare GmbH",
            "Biospecimen Solutions",
            "Boca Biolistics GmbH",
            "Central BioHub GmbH",
            "Cerba",
            "GBD",
            "Hiss-DX",
            "in.vent Diagnostica GmbH",
            "INO Specimens BioBank",
            "Instand e.V.",
            "Labor Brunner",
            "Labor Froreich",
            "Labor Hartinger",
            "Labor Mauff",
            "Logical Biological",
            "Med.Labor Ostsachsen(Görlitz)",
            "microBIOMix GmbH",
            "MIKROGEN internal",
            "Munich Airport Test & Fly Center",
            "MVZ Labor Lademannbogen",
            "MVZ Labor Ludwigsburg",
            "MVZ Labor Poing",
            "Paul - Ehrlich - Institut",
            "Precision for Medicine",
            "QCMD",
            "SampleSmart",
            "Synlab München",
            "UKW Würzburg",
            "Vircell",
            ]
        self.stdout.write('Adding Providers...')
        for name in providers:
            obj, created = Provider.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f'  - Added: {name}')
            else:
                self.stdout.write(f'  - Already exists: {name}')

        # Add Targets
        targets = [
            # Add your specific targets here
            "Campylobacter coli",
            "Campylobacter jejuni",
            "Campylobacter lari",
            "Campylobacter fetus",
            "Campylobacter upsaliensis",
            "Salmonella spp.",
            "Yersinia enterocolitica",
            "Yersinia enterocolitica BT1A",
            "Escherichia coli VTEC",
            "Escherichia coli EPEC",
            "Escherichia coli ETEC",
            "Escherichia coli EAEC",
            "Shigella EIEC",
            "Norovirus",
            "Rotavirus",
            "Adenovirus",
            "Sapovirus",
            "Astrovirus",
            "Chlamydophila pneumoniae",
            "Mycoplasma pneumoniae",
            "Legionella pneumophila",
            "Legionella spp.",
            "Bordetella pertussis",
            "Bordetella parapertussis",
            "Bordetella holmesii",
            "Streptococcus pneumoniae",
            "Staphylococcus aureus",
            "Haemophilus influenzae",
            "Moraxella catarrhalis",
            "Klebsiella pneumoniae",
            "Klebsiella oxytoca",
            "Klebsiella michiganensis",
            "Influenza A",
            "Influenza B",
            "Influenza A H1N1",
            "Parainfluenza 1",
            "Parainfluenza 2",
            "Parainfluenza 3",
            "Parainfluenza 4",
            "Bocavirus",
            "Parechovirus",
            "Metapneumovirus",
            "RSVa",
            "RSVb",
            "Rhinovirus",
            "Enterovirus",
            "Adenovirus",
            "Corona Virus MERS",
            "Corona Virus OC432",
            "Corona Virus HKU12",
            "Corona Virus E229",
            "Corona Virus NL63",
            "Coronavirus SARS",
            "Coronavirus SARS-CoV-2",
            "Chlamydia trachomatis",
            "Neisseria gonorrhoeae",
            "Mycoplasma genitalium",
            "Trichomonas vaginalis",
            "Mycoplasma hominis",
            "Ureaplasma ureayticum",
            "Ureaplasma parvum",
            "Herpes Simplex Virus",
            "Treponema pallidum",
            "HEV",
        ]
        self.stdout.write('Adding Targets...')
        for name in targets:
            obj, created = Target.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f'  - Added: {name}')
            else:
                self.stdout.write(f'  - Already exists: {name}')

        # Add Storage Places with types
        storage_places = [
            # Room locations
            ("Room 3311: Kühlschrankraum", "room", None),
            ("Room 3305: SetUp Raum 2", "room", None),
            # Freezer locations
            ("Freezer A", "freezer", "Room 3311: Kühlschrankraum"),
            ("Freezer B", "freezer", "Room 3311: Kühlschrankraum"),
            ("Freezer C", "freezer", "Room 3305: SetUp Raum 2"),
            # Drawer locations
            ("Drawer 1", "drawer", "Freezer A"),
            ("Drawer 2", "drawer", "Freezer A"),
            ("Drawer 3", "drawer", "Freezer B"),
            # Box locations
            ("Box A1", "box", "Drawer 1"),
            ("Box A2", "box", "Drawer 1"),
            ("Box B1", "box", "Drawer 2"),
            ("Box B2", "box", "Drawer 3"),
        ]

        self.stdout.write('Adding Storage Places...')
        # First pass - create rooms which have no parents
        room_objects = {}
        for name, type_value, parent_name in storage_places:
            if type_value == 'room':
                obj, created = StoragePlace.objects.get_or_create(name=name, type=type_value)
                room_objects[name] = obj
                if created:
                    self.stdout.write(f'  - Added: {name} ({type_value})')
                else:
                    self.stdout.write(f'  - Already exists: {name} ({type_value})')

        # Second pass - create freezers with room parents
        freezer_objects = {}
        for name, type_value, parent_name in storage_places:
            if type_value == 'freezer':
                parent = room_objects.get(parent_name)
                if parent:
                    obj, created = StoragePlace.objects.get_or_create(
                        name=name,
                        type=type_value,
                        defaults={'parent': parent}
                    )
                    freezer_objects[name] = obj
                    if created:
                        self.stdout.write(f'  - Added: {name} ({type_value}) in {parent_name}')
                    else:
                        # Make sure parent is set even if object already exists
                        if obj.parent != parent:
                            obj.parent = parent
                            obj.save()
                        self.stdout.write(f'  - Already exists: {name} ({type_value})')

        # Third pass - create drawers with freezer parents
        drawer_objects = {}
        for name, type_value, parent_name in storage_places:
            if type_value == 'drawer':
                parent = freezer_objects.get(parent_name)
                if parent:
                    obj, created = StoragePlace.objects.get_or_create(
                        name=name,
                        type=type_value,
                        defaults={'parent': parent}
                    )
                    drawer_objects[name] = obj
                    if created:
                        self.stdout.write(f'  - Added: {name} ({type_value}) in {parent_name}')
                    else:
                        # Make sure parent is set even if object already exists
                        if obj.parent != parent:
                            obj.parent = parent
                            obj.save()
                        self.stdout.write(f'  - Already exists: {name} ({type_value})')

        # Fourth pass - create boxes with drawer parents
        for name, type_value, parent_name in storage_places:
            if type_value == 'box':
                parent = drawer_objects.get(parent_name)
                if parent:
                    obj, created = StoragePlace.objects.get_or_create(
                        name=name,
                        type=type_value,
                        defaults={'parent': parent}
                    )
                    if created:
                        self.stdout.write(f'  - Added: {name} ({type_value}) in {parent_name}')
                    else:
                        # Make sure parent is set even if object already exists
                        if obj.parent != parent:
                            obj.parent = parent
                            obj.save()
                        self.stdout.write(f'  - Already exists: {name} ({type_value})')

        # Add Extractors
        extractors = [
            # Add your specific extractors here
            "MP96",
            "MP24",
            "MP Compact",
            "Biocomma 32",
            "Biocomma 48",
            "Biocomma 96",
            "L VIII",
            "Z2",
            "Prime MDx",
            "AmpliCube (Hamilton)",
            # Add more...
        ]
        self.stdout.write('Adding Extractors...')
        for name in extractors:
            obj, created = Extractor.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f'  - Added: {name}')
            else:
                self.stdout.write(f'  - Already exists: {name}')

        # Add Cyclers
        cyclers = [
            # Add your specific cyclers here
            "LC480II",
            "Cobas z 480",
            "CFX96",
            "QS5",
            "Mic RUO / IVD",
            "Rotorgene"
            "LC Pro"
            "qTower"
            "Prime MDx"
            "GL VIII",
            # Add more...
        ]
        self.stdout.write('Adding Cyclers...')
        for name in cyclers:
            obj, created = Cycler.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f'  - Added: {name}')
            else:
                self.stdout.write(f'  - Already exists: {name}')

        # Add PCR Kits - Mikrogen
        mikrogen_kits = [
            # Add your specific Mikrogen PCR kits here
            "Mikrogen Kit A",
            "Mikrogen Kit B",
            # Add more...
        ]
        self.stdout.write('Adding Mikrogen PCR Kits...')
        for name in mikrogen_kits:
            obj, created = PCRKit.objects.get_or_create(name=name, type='mikrogen')
            if created:
                self.stdout.write(f'  - Added: {name}')
            else:
                self.stdout.write(f'  - Already exists: {name}')

        # Add PCR Kits - External
        external_kits = [
            # Add your specific External PCR kits here
            "External Kit A",
            "External Kit B",
            # Add more...
        ]
        self.stdout.write('Adding External PCR Kits...')
        for name in external_kits:
            obj, created = PCRKit.objects.get_or_create(name=name, type='external')
            if created:
                self.stdout.write(f'  - Added: {name}')
            else:
                self.stdout.write(f'  - Already exists: {name}')

        self.stdout.write(self.style.SUCCESS('Successfully added initial data'))
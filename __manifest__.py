{
    'name': 'Elmi Logistics Fleet Management System',
    'version': '19.0.1.0.0',
    'category': 'Logistics/Fleet',
    'summary': 'Elmi Olindo Comprehensive Fleet Management with GPS Telematics, Fuel Analytics & Trip Execution',
    'description': """
Elmi Logistics Fleet Management System
======================================

Enterprise-grade fleet management module for Odoo 19 with:

* Transport Request Workflow (Draft → Approval → Assignment → Dispatch → Completion)
* Vehicle & Driver Availability Validation
* GPS Telematics Integration (Wialon, Teltonika, Concox)
* Real-Time Vehicle Tracking & Safety Events
* Fuel Consumption Analysis (GPS vs Benchmark vs Refuel)
* Pre-Trip & Post-Trip Inspection Checklists
* Cost Analytics (Cost per KM, Cost per Trip, Utilization Rate)
* Automated Alerts (Document Expiry, Maintenance Due, GPS Offline)
* Executive Dashboards with Real-Time KPIs
* Accident & Incident Management with Insurance Claims

Fully compliant with ISO 15614 Fleet Management Standards.
    """,
    'author': 'Elmi Olindo Contractors PLC',
    'website': 'https://www.topengineering.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'fleet',
        'hr',
        'web',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',

        # Data
        'data/ir_sequence_data.xml',
        # 'data/activity_types.xml',  # Temporarily disabled - will enable after server restart
        'data/mail_template.xml',
        'data/ir_cron_data.xml',
        'data/request_type_data.xml',
        'data/trip_type_data.xml',
        'data/master_data.xml',

        # Wizards
        'views/transport_request_reject_wizard_views.xml',
        'views/vehicle_assignment_wizard_views.xml',
        'views/fleet_dispatch_wizard_views.xml',
        'views/trip_return_wizard_views.xml',
        'views/fuel_consumption_report_wizard_views.xml',
        'views/fleet_enroute_stop_wizard_views.xml',
        'views/top_site_log_import_wizard_views.xml',

        # Views
        'views/transport_request_views.xml',
        'views/transport_request_type_views.xml',
        'views/fleet_trip_views.xml',
        'views/machinery_deployment_order_views.xml',
        'views/fleet_meter_reading_views.xml',
        'views/fleet_trip_type_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/hr_employee_views.xml',
        'views/vehicle_inspection_views.xml',
        'views/gps_device_views.xml',
        'views/gps_provider_views.xml',
        'views/gps_event_views.xml',
        'views/gps_position_views.xml',
        'views/gps_geofence_views.xml',
        'views/fleet_fuel_log_views.xml',
        'views/fleet_fuel_analysis_views.xml',
        'views/gps_fuel_transaction_views.xml',
        'views/fleet_accident_views.xml',
        'views/logistics_location_views.xml',
        'views/alert_config_views.xml',
        'views/dashboard_views.xml',
        'views/fleet_map_views.xml',
        'views/fleet_activity_report_views.xml',
        'views/menus.xml',

        # Reports
        'reports/trip_report.xml',
        'reports/fleet_utilization.xml',
        'reports/fuel_report.xml',
        'reports/fleet_fuel_efficiency_report.xml',
        'reports/fleet_activity_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'elmi_logistics_fleet/static/src/css/transport_request.css',
            'elmi_logistics_fleet/static/src/css/logistics_dashboard.css',
            'elmi_logistics_fleet/static/src/css/vehicle_dashboard.css',
            'elmi_logistics_fleet/static/src/xml/logistics_dashboard.xml',
            'elmi_logistics_fleet/static/src/xml/vehicle_dashboard.xml',
            'elmi_logistics_fleet/static/src/js/logistics_dashboard.js',
            'elmi_logistics_fleet/static/src/js/vehicle_dashboard.js',
        ],
    },
    'demo': [
        'demo/demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FleetTrip(models.Model):
    _name = 'top.fleet.trip'
    _description = 'Fleet Trip Execution'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'planned_departure desc, id desc'

    name = fields.Char(
        string='Trip Number',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
    )
    request_id = fields.Many2one(
        'top.transport.request',
        string='Transport Request',
        ondelete='restrict',
        tracking=True,
        index=True,
    )
    request_ids = fields.Many2many(
        'top.transport.request',
        'top_trip_request_rel',
        'trip_id',
        'request_id',
        string='Consolidated Transport Requests',
        help='Multiple transport requests served together in this consolidated transport order.',
    )
    fleet_order_type = fields.Selection([
        ('light', 'Light Fleet'),
        ('heavy', 'Heavy Fleet'),
    ], string='Fleet Order Type', default='light', tracking=True)
    inspection_id = fields.Many2one(
        'top.fleet.vehicle.inspection',
        string='Pre-Trip Vehicle Inspection',
        tracking=True,
        help='Technical condition inspection record conducted prior to dispatch.',
    )
    trip_type_id = fields.Many2one(
        'top.fleet.trip.type',
        string='Trip Type',
        tracking=True,
    )
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle',
        required=True,
        tracking=True,
        index=True,
    )
    vehicle_last_service_date = fields.Date(
        related='vehicle_id.last_service_date',
        string='Vehicle Last Service Date',
        readonly=True,
    )
    vehicle_next_service_date = fields.Date(
        related='vehicle_id.next_service_date',
        string='Vehicle Next Service Due',
        readonly=True,
    )
    vehicle_service_status = fields.Selection(
        related='vehicle_id.service_status',
        string='Vehicle Service Status',
        readonly=True,
    )
    driver_id = fields.Many2one(
        'hr.employee',
        string='Assigned Driver',
        required=True,
        tracking=True,
        index=True,
        help='Driver assigned to this trip. Auto-filled if vehicle has dedicated driver, or select from all employees.',
    )
    driver_license_expiry_date = fields.Date(
        related='driver_id.license_expiry_date',
        string='Driver License Expiration',
        readonly=True,
    )
    driver_is_license_expired = fields.Boolean(
        related='driver_id.is_license_expired',
        string='Driver License Expired',
        readonly=True,
    )
    driver_license_compliance = fields.Char(
        related='driver_id.license_compliance_status',
        string='Driver License Status',
        readonly=True,
    )
    backup_driver_id = fields.Many2one(
        'hr.employee',
        string='Backup Driver',
        help='Optional backup driver selected from all employees.',
    )
    trip_coordinator_id = fields.Many2one(
        'res.users',
        string='Trip Coordinator',
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )

    # Route & Schedule (Sections 14 & 16)
    origin_location_id = fields.Many2one(
        'top.logistics.location',
        string='Origin Location',
        tracking=True,
    )
    destination_location_id = fields.Many2one(
        'top.logistics.location',
        string='Destination Location',
        tracking=True,
    )
    origin = fields.Char(string='Origin', required=True)
    destination = fields.Char(string='Destination', required=True)
    waypoint_ids = fields.One2many(
        'top.fleet.trip.waypoint',
        'trip_id',
        string='Waypoints / Stops',
    )
    total_stops_count = fields.Integer(
        string='Total Stops Planned',
        compute='_compute_stop_metrics',
        store=True,
    )
    completed_stops_count = fields.Integer(
        string='Stops Completed',
        compute='_compute_stop_metrics',
        store=True,
    )
    cancelled_stops_count = fields.Integer(
        string='Stops Cancelled',
        compute='_compute_stop_metrics',
        store=True,
    )
    pending_stops_count = fields.Integer(
        string='Stops Pending',
        compute='_compute_stop_metrics',
        store=True,
    )
    planned_departure = fields.Datetime(string='Planned Departure', required=True, tracking=True)
    planned_arrival = fields.Datetime(string='Planned Arrival', required=True, tracking=True)
    actual_departure = fields.Datetime(string='Actual Departure', tracking=True)
    actual_arrival = fields.Datetime(string='Actual Arrival', tracking=True)
    purpose = fields.Text(string='Trip Purpose')
    special_instructions = fields.Text(string='Special Instructions / Notes')

    # Distance & Duration Metrics
    planned_distance = fields.Float(string='Planned Distance (km)')
    initial_planned_distance = fields.Float(string='Initial Planned Distance (km)', copy=False, help='Initial distance planned before any en-route modifications.')
    enroute_distance_added = fields.Float(string='En-Route Distance Added (km)', default=0.0, copy=False, help='Net distance added by en-route stop modifications.')
    actual_distance = fields.Float(string='Actual Distance (km)', compute='_compute_actual_distance', store=True, readonly=False, tracking=True)

    # TWO Blueprint Consolidation & Amendments
    amendment_ids = fields.One2many(
        'top.two.amendment',
        'two_id',
        string='Trip Leg Amendments',
    )
    amendment_count = fields.Integer(compute='_compute_amendment_count')
    emergency_fuel_pct = fields.Float(
        string='Emergency Fuel Buffer (%)',
        default=5.0,
        help='Configurable emergency buffer added to computed fuel requirement (e.g. +5%).',
    )
    is_outsourced = fields.Boolean(
        string='Outsourced / Rental Service',
        default=False,
        tracking=True,
    )
    rental_note = fields.Text(string='Unavailable Resources / Rental Justification')
    planned_duration = fields.Float(string='Planned Duration (Hours)')
    actual_duration = fields.Float(string='Actual Duration (Hours)', compute='_compute_actual_duration', store=True)
    actual_duration_display = fields.Char(string='Time Taken Display', compute='_compute_actual_duration_display')

    # Fuel & Operating Costs (Sections 30, 31, 32)
    expected_fuel = fields.Float(string='Planned Fuel (L)', compute='_compute_expected_fuel', store=True, readonly=False, help='Estimated fuel required for planned distance.')
    fuel_log_ids = fields.One2many('top.fleet.fuel.log', 'trip_id', string='Fuel Logs')
    total_refueled = fields.Float(string='Total Refueled (L)', compute='_compute_fuel_metrics', store=True, help='Total litres purchased and added to tank during this trip from fuel logs.')
    fuel_consumed_gps = fields.Float(string='GPS Fuel Consumed (L)', compute='_compute_fuel_metrics', store=True, help='Fuel consumed measured by GPS tank drop plus refuels: (Start Fuel + Refueled) - End/Current Fuel.')
    fuel_consumed_norm = fields.Float(string='Benchmark Norm Fuel (L)', compute='_compute_fuel_metrics', store=True, help='Estimated consumption using vehicle standard rate: (Actual Distance * Benchmark Rate) / 100.')
    fuel_consumption_method = fields.Selection([
        ('gps', 'GPS Sensor Telemetry'),
        ('norm', 'Benchmark Consumption Norm'),
        ('refuel', 'Refueling Purchases'),
    ], string='Fuel Measurement Method', compute='_compute_fuel_metrics', store=True)
    actual_fuel = fields.Float(string='Actual Fuel Consumed (L)', compute='_compute_fuel_metrics', store=True, tracking=True)
    total_fuel_cost = fields.Float(string='Purchased Fuel Cost', compute='_compute_fuel_metrics', store=True)
    consumed_fuel_cost = fields.Float(string='Consumed Fuel Value', compute='_compute_fuel_metrics', store=True)
    fuel_theft_suspected = fields.Boolean(string='Abnormal Fuel Drain / Potential Leak', compute='_compute_fuel_metrics', store=True)
    total_trip_cost = fields.Float(string='Total Trip Cost', compute='_compute_trip_costs', store=True)
    cost_per_km = fields.Float(string='Trip Cost / KM', compute='_compute_trip_costs', store=True)
    fuel_consumption_rate = fields.Float(string='Fuel Rate (L/100km)', compute='_compute_trip_costs', store=True)
    fuel_economy_kml = fields.Float(string='Fuel Economy (km/L)', compute='_compute_trip_costs', store=True, help='Distance traveled per litre of fuel consumed.')
    gross_fuel = fields.Float(string='Gross Fuel (Start + Refueled)', compute='_compute_gross_fuel', store=True, help='Initial tank fuel at dispatch plus all refuels along the trip.')
    sub_trips_count = fields.Integer(string='Sub-Trips / Legs Count', compute='_compute_sub_trips_metrics', store=True, help='Total legs including intermediate waypoint stops.')
    sub_trips_route_display = fields.Char(string='Full Route (Sub-Trips)', compute='_compute_sub_trips_metrics', store=True)

    # Reconciliation Variances (Section 29)
    variance_distance = fields.Float(string='Distance Variance (km)', compute='_compute_variances', store=True)
    variance_duration = fields.Float(string='Duration Variance (Hours)', compute='_compute_variances', store=True)
    variance_fuel = fields.Float(string='Fuel Variance (L)', compute='_compute_variances', store=True)

    # GPS Telemetry & Tracking (Sections 14, 18, 26)
    gps_device_id = fields.Many2one(
        'top.gps.device',
        string='GPS Device',
        compute='_compute_gps_device',
        store=True,
    )
    gps_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('no_device', 'No Device Attached'),
    ], string='GPS Status', compute='_compute_gps_status', store=True)

    current_latitude = fields.Float(related='gps_device_id.latitude', string='Live Latitude', readonly=True)
    current_longitude = fields.Float(related='gps_device_id.longitude', string='Live Longitude', readonly=True)
    current_speed = fields.Float(related='gps_device_id.speed', string='Live Speed (km/h)', readonly=True)
    current_odometer = fields.Float(related='gps_device_id.odometer', string='Live GPS Odometer', readonly=True)
    current_address = fields.Char(related='gps_device_id.address', string='Current Location', readonly=True)
    current_fuel = fields.Float(
        string='Current Fuel (L)',
        compute='_compute_current_fuel',
        readonly=True,
        help='Current live fuel level from vehicle GPS tracker.',
    )
    vehicle_to_origin_distance = fields.Float(
        string='Vehicle to Pickup (km)',
        compute='_compute_vehicle_to_origin_distance',
        help='Live distance from assigned vehicle current GPS position to trip origin.'
    )

    event_ids = fields.One2many('top.gps.event', 'trip_id', string='GPS Events / Alerts')
    position_ids = fields.One2many('top.gps.position', 'trip_id', string='Trip Track Points')

    # Pre-Dispatch Vehicle Condition Checklist (Section 17 & 35)
    chk_tires = fields.Boolean(string='Tires Condition & Pressure Checked', default=True)
    chk_engine = fields.Boolean(string='Engine Sound & Operation Checked', default=True)
    chk_oil = fields.Boolean(string='Engine Oil Level Checked', default=True)
    chk_coolant = fields.Boolean(string='Coolant & Radiator Level Checked', default=True)
    chk_brakes = fields.Boolean(string='Foot & Hand Brakes Tested', default=True)
    chk_lights = fields.Boolean(string='Headlights, Indicators & Brake Lights Checked', default=True)
    chk_spare_tire = fields.Boolean(string='Spare Tire Present & Inflated', default=True)
    chk_tools = fields.Boolean(string='Vehicle Jack & Tools Present', default=True)
    chk_fire_extinguisher = fields.Boolean(string='Fire Extinguisher Valid & Present', default=True)
    chk_first_aid = fields.Boolean(string='First Aid Kit Present', default=True)
    chk_body_condition = fields.Boolean(string='Body Condition Inspected (No Unrecorded Dents)', default=True)

    # General Pre-Dispatch confirmations
    chk_vehicle_inspected = fields.Boolean(string='Vehicle Inspection Confirmed')
    chk_fuel_checked = fields.Boolean(string='Fuel Level Checked')
    chk_driver_confirmed = fields.Boolean(string='Driver Briefed & Confirmed')
    chk_gps_online = fields.Boolean(string='GPS Tracker Online & Active')
    chk_documents_valid = fields.Boolean(string='Vehicle & Driver Documents Physically Checked')
    chk_emergency_equipment = fields.Boolean(string='Emergency Kit & Fire Extinguisher Present')
    start_odometer = fields.Float(string='Starting Odometer (km)')
    start_fuel = fields.Float(string='Starting Fuel Level (L)', tracking=True, help='Initial fuel in vehicle tank in Litres when dispatched.')
    start_fuel_level = fields.Selection([
        ('quarter', '1/4 Tank'),
        ('half', '1/2 Tank'),
        ('three_quarter', '3/4 Tank'),
        ('full', 'Full Tank'),
    ], string='Starting Fuel Level')
    dispatched_by_id = fields.Many2one('res.users', string='Dispatched By', readonly=True)
    dispatch_date = fields.Datetime(string='Dispatch Timestamp', readonly=True)

    # Post-Trip Return Checklist (Section 36)
    vehicle_returned = fields.Boolean(string='Vehicle Returned to Depot', readonly=True)
    end_odometer = fields.Float(string='Ending Odometer (km)', readonly=True)
    end_fuel = fields.Float(string='Ending Fuel Level (L)', tracking=True, readonly=True, help='Final fuel in vehicle tank in Litres upon return inspection.')
    end_fuel_level = fields.Selection([
        ('quarter', '1/4 Tank'),
        ('half', '1/2 Tank'),
        ('three_quarter', '3/4 Tank'),
        ('full', 'Full Tank'),
    ], string='Ending Fuel Gauge', readonly=True)
    return_cleanliness = fields.Selection([
        ('clean', 'Clean / Satisfactory'),
        ('acceptable', 'Normal Dust / Acceptable'),
        ('needs_wash', 'Dirty / Requires Wash'),
    ], string='Cleanliness Status', readonly=True)
    has_damage = fields.Boolean(string='New Damage Flagged', readonly=True)
    damage_description = fields.Text(string='Observed Return Damage', readonly=True)
    missing_equipment = fields.Char(string='Missing Equipment / Tools', readonly=True)
    new_defects = fields.Text(string='New Defects Reported', readonly=True)
    driver_comments = fields.Text(string='Driver Debrief Notes', readonly=True)
    accident_id = fields.Many2one('top.fleet.accident', string='Incident Record', readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('ready', 'Ready / Assigned'),
        ('dispatched', 'Dispatched'),
        ('in_transit', 'In Transit'),
        ('completed', 'Completed'),
        ('reconciled', 'Reconciled'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Trip Status', default='draft', readonly=True, tracking=True, index=True, copy=False)

    @api.onchange('origin_location_id')
    def _onchange_origin_location_id(self):
        if self.origin_location_id:
            self.origin = self.origin_location_id.display_name or self.origin_location_id.name
        self._calculate_route_distance()

    @api.onchange('destination_location_id')
    def _onchange_destination_location_id(self):
        if self.destination_location_id:
            self.destination = self.destination_location_id.display_name or self.destination_location_id.name
        self._calculate_route_distance()

    @api.onchange('waypoint_ids')
    def _onchange_waypoint_ids(self):
        self._calculate_route_distance()

    def _calculate_route_distance(self):
        """Auto-computes route planned distance, duration, and planned fuel from coordinates."""
        for trip in self:
            points = []
            if trip.origin_location_id and trip.origin_location_id.latitude and trip.origin_location_id.longitude:
                points.append((trip.origin_location_id.latitude, trip.origin_location_id.longitude))

            for wp in trip.waypoint_ids.sorted(key=lambda w: (w.sequence, w.id)):
                if wp.location_id and wp.location_id.latitude and wp.location_id.longitude:
                    points.append((wp.location_id.latitude, wp.location_id.longitude))

            if trip.destination_location_id and trip.destination_location_id.latitude and trip.destination_location_id.longitude:
                points.append((trip.destination_location_id.latitude, trip.destination_location_id.longitude))

            if len(points) >= 2:
                metrics = self.env['top.logistics.location'].calculate_route_metrics(points)
                if metrics.get('distance_km', 0) > 0:
                    trip.planned_distance = metrics['distance_km']
                    trip.planned_duration = metrics['duration_hours']
                    rate = trip.vehicle_id.expected_fuel_consumption or 12.0
                    trip.expected_fuel = round((trip.planned_distance * rate) / 100.0, 2)

    def action_calculate_route_distance(self):
        """Action button to trigger automatic distance calculation."""
        self._calculate_route_distance()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Route Distance Calculated"),
                'message': _("Calculated Distance: %s km | Estimated Duration: %s hours | Planned Fuel: %s L") % (
                    self.planned_distance, self.planned_duration, self.expected_fuel
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.depends('waypoint_ids.state', 'waypoint_ids.completed')
    def _compute_stop_metrics(self):
        for trip in self:
            trip.total_stops_count = len(trip.waypoint_ids)
            trip.completed_stops_count = len(trip.waypoint_ids.filtered(lambda w: w.state == 'completed' or w.completed))
            trip.cancelled_stops_count = len(trip.waypoint_ids.filtered(lambda w: w.state == 'cancelled'))
            trip.pending_stops_count = len(trip.waypoint_ids.filtered(lambda w: w.state == 'pending' and not w.completed))

    @api.depends('actual_duration')
    def _compute_actual_duration_display(self):
        for trip in self:
            if trip.actual_duration:
                total_hours = trip.actual_duration
                hrs = int(total_hours)
                mins = int(round((total_hours - hrs) * 60))
                trip.actual_duration_display = f"{hrs}h {mins}m"
            else:
                trip.actual_duration_display = _("0h 0m")

    @api.depends('start_odometer', 'end_odometer')
    def _compute_actual_distance(self):
        for trip in self:
            if trip.end_odometer and trip.start_odometer and trip.end_odometer >= trip.start_odometer:
                trip.actual_distance = round(trip.end_odometer - trip.start_odometer, 2)
            elif not trip.actual_distance:
                trip.actual_distance = 0.0

    @api.depends('planned_distance', 'vehicle_id.expected_fuel_consumption')
    def _compute_expected_fuel(self):
        for trip in self:
            rate = trip.vehicle_id.expected_fuel_consumption or 12.0
            if trip.planned_distance:
                trip.expected_fuel = round((trip.planned_distance * rate) / 100.0, 2)
            elif not trip.expected_fuel:
                trip.expected_fuel = 0.0

    @api.depends(
        'fuel_log_ids.quantity', 'fuel_log_ids.total_cost',
        'start_fuel', 'end_fuel', 'vehicle_id.live_fuel_level',
        'actual_distance', 'state', 'vehicle_id.expected_fuel_consumption',
        'start_odometer', 'end_odometer', 'planned_distance'
    )
    def _compute_fuel_metrics(self):
        recent_log = self.env['top.fleet.fuel.log'].search([], order='date desc, id desc', limit=1)
        fallback_price = recent_log.unit_price if (recent_log and recent_log.unit_price) else 100.0

        for trip in self:
            refueled = sum(trip.fuel_log_ids.mapped('quantity'))
            refuel_cost = sum(trip.fuel_log_ids.mapped('total_cost'))
            trip.total_refueled = round(refueled, 2)
            trip.total_fuel_cost = round(refuel_cost, 2)

            # Determine distance (actual or odo diff or planned)
            dist = trip.actual_distance or (trip.end_odometer - trip.start_odometer if (trip.end_odometer and trip.start_odometer and trip.end_odometer > trip.start_odometer) else 0.0) or trip.planned_distance or 0.0

            # Determine start fuel
            start_f = trip.start_fuel or 0.0
            if start_f <= 0.0 and trip.vehicle_id.live_fuel_level:
                start_f = trip.vehicle_id.live_fuel_level

            # Determine current/terminal fuel level in tank
            if trip.state in ['completed', 'reconciled', 'closed']:
                terminal_fuel = trip.end_fuel if (trip.end_fuel and trip.end_fuel > 0.0) else (trip.vehicle_id.live_fuel_level or 0.0)
            elif trip.state in ['dispatched', 'in_transit']:
                terminal_fuel = trip.vehicle_id.live_fuel_level or (trip.gps_device_id.fuel_level if trip.gps_device_id else 0.0) or 0.0
            else:
                terminal_fuel = start_f

            # 1. GPS Consumption: (start_fuel + refueled) - terminal_fuel
            if start_f > 0.0 and terminal_fuel > 0.0 and (start_f + refueled) >= terminal_fuel:
                gps_consumed = max(0.0, (start_f + refueled) - terminal_fuel)
            else:
                gps_consumed = 0.0
            trip.fuel_consumed_gps = round(gps_consumed, 2)

            # 2. Benchmark Norm Consumption: (actual_distance * expected_rate) / 100
            rate = trip.vehicle_id.expected_fuel_consumption or 12.0
            norm_consumed = round((dist * rate) / 100.0, 2) if dist > 0.0 else 0.0
            trip.fuel_consumed_norm = norm_consumed

            # 3. Choose primary actual fuel consumed
            if gps_consumed > 0.0:
                trip.actual_fuel = round(gps_consumed, 2)
                trip.fuel_consumption_method = 'gps'
            elif norm_consumed > 0.0:
                trip.actual_fuel = round(norm_consumed, 2)
                trip.fuel_consumption_method = 'norm'
            elif refueled > 0.0:
                trip.actual_fuel = round(refueled, 2)
                trip.fuel_consumption_method = 'refuel'
            else:
                trip.actual_fuel = 0.0
                trip.fuel_consumption_method = 'gps' if (start_f > 0 and terminal_fuel > 0) else 'norm'

            # 4. Monetary value of consumed fuel
            unit_price = (refuel_cost / refueled) if refueled > 0.0 else fallback_price
            trip.consumed_fuel_cost = round(trip.actual_fuel * unit_price, 2)

            # 5. Suspected fuel loss / siphoning alert
            if trip.fuel_consumption_method == 'gps' and norm_consumed > 0.0 and trip.actual_fuel > 0.0:
                excess = trip.actual_fuel - norm_consumed
                trip.fuel_theft_suspected = bool(excess > 15.0 and (trip.actual_fuel / norm_consumed) >= 1.35)
            else:
                trip.fuel_theft_suspected = False

    @api.depends('start_fuel', 'total_refueled')
    def _compute_gross_fuel(self):
        for trip in self:
            trip.gross_fuel = round((trip.start_fuel or 0.0) + (trip.total_refueled or 0.0), 2)

    @api.depends('origin', 'destination', 'waypoint_ids', 'waypoint_ids.location_name')
    def _compute_sub_trips_metrics(self):
        for trip in self:
            wps = trip.waypoint_ids.sorted(key=lambda w: (w.sequence, w.id))
            trip.sub_trips_count = len(wps) + 1
            route_parts = [trip.origin or _("Origin")]
            for wp in wps:
                if wp.location_name:
                    route_parts.append(wp.location_name)
            route_parts.append(trip.destination or _("Destination"))
            trip.sub_trips_route_display = " ➔ ".join(route_parts)

    @api.depends('total_fuel_cost', 'consumed_fuel_cost', 'actual_distance', 'actual_fuel', 'planned_distance', 'start_odometer', 'end_odometer')
    def _compute_trip_costs(self):
        for trip in self:
            trip.total_trip_cost = trip.consumed_fuel_cost if trip.consumed_fuel_cost > 0.0 else trip.total_fuel_cost
            dist = trip.actual_distance or (trip.end_odometer - trip.start_odometer if (trip.end_odometer and trip.start_odometer and trip.end_odometer > trip.start_odometer) else 0.0) or trip.planned_distance or 0.0
            if dist > 0.0:
                trip.cost_per_km = round(trip.total_trip_cost / dist, 2)
                trip.fuel_consumption_rate = round((trip.actual_fuel / dist) * 100.0, 2)
                trip.fuel_economy_kml = round(dist / trip.actual_fuel, 2) if trip.actual_fuel > 0.0 else 0.0
            else:
                trip.cost_per_km = 0.0
                trip.fuel_consumption_rate = 0.0
                trip.fuel_economy_kml = 0.0

    @api.onchange('planned_distance', 'vehicle_id')
    def _onchange_planned_distance(self):
        if self.vehicle_id:
            assigned_drv = self.vehicle_id.get_assigned_driver()
            if assigned_drv:
                self.driver_id = assigned_drv.id
        if self.planned_distance and self.vehicle_id:
            rate = self.vehicle_id.expected_fuel_consumption or 12.0
            if not self.expected_fuel or self.expected_fuel == 0.0:
                self.expected_fuel = round((self.planned_distance * rate) / 100.0, 2)

    @api.depends('actual_distance', 'planned_distance', 'actual_duration', 'planned_duration', 'actual_fuel', 'expected_fuel', 'start_odometer', 'end_odometer')
    def _compute_variances(self):
        for trip in self:
            # Section 29 Reconciliation Formulas
            dist = trip.actual_distance or (trip.end_odometer - trip.start_odometer if (trip.end_odometer and trip.start_odometer and trip.end_odometer > trip.start_odometer) else 0.0) or (trip.planned_distance or 0.0)
            trip.variance_distance = round(dist - (trip.planned_distance or 0.0), 2)
            trip.variance_duration = round((trip.actual_duration or 0.0) - (trip.planned_duration or 0.0), 2)
            trip.variance_fuel = round((trip.actual_fuel or 0.0) - (trip.expected_fuel or 0.0), 2)

    @api.depends('vehicle_id', 'vehicle_id.gps_device_id')
    def _compute_gps_device(self):
        for trip in self:
            trip.gps_device_id = trip.vehicle_id.gps_device_id if trip.vehicle_id else False

    @api.depends('gps_device_id', 'gps_device_id.status')
    def _compute_gps_status(self):
        for trip in self:
            if not trip.gps_device_id:
                trip.gps_status = 'no_device'
            elif trip.gps_device_id.status == 'active':
                trip.gps_status = 'online'
            else:
                trip.gps_status = 'offline'

    @api.depends('vehicle_id.live_fuel_level', 'gps_device_id.fuel_level')
    def _compute_current_fuel(self):
        for trip in self:
            trip.current_fuel = (
                trip.vehicle_id.live_fuel_level
                or (trip.gps_device_id and trip.gps_device_id.fuel_level)
                or 0.0
            )

    @api.depends('vehicle_id', 'vehicle_id.gps_device_id', 'current_latitude', 'current_longitude', 'origin_location_id', 'origin_location_id.latitude', 'origin_location_id.longitude')
    def _compute_vehicle_to_origin_distance(self):
        for trip in self:
            if trip.vehicle_id and trip.current_latitude and trip.current_longitude and trip.origin_location_id and trip.origin_location_id.latitude and trip.origin_location_id.longitude:
                dist = self.env['top.logistics.location'].calculate_distance_km(
                    trip.current_latitude, trip.current_longitude,
                    trip.origin_location_id.latitude, trip.origin_location_id.longitude
                )
                trip.vehicle_to_origin_distance = dist
            else:
                trip.vehicle_to_origin_distance = 0.0

    @api.depends('actual_departure', 'actual_arrival')
    def _compute_actual_duration(self):
        for trip in self:
            if trip.actual_departure and trip.actual_arrival:
                delta = trip.actual_arrival - trip.actual_departure
                trip.actual_duration = round(delta.total_seconds() / 3600.0, 2)
            else:
                trip.actual_duration = 0.0

    @api.constrains('planned_departure', 'planned_arrival')
    def _check_planned_dates(self):
        for trip in self:
            if trip.planned_departure and trip.planned_arrival and trip.planned_arrival < trip.planned_departure:
                raise ValidationError(_("Planned arrival (%s) cannot be earlier than planned departure (%s).") % (
                    trip.planned_arrival, trip.planned_departure
                ))

    @api.depends('amendment_ids')
    def _compute_amendment_count(self):
        for rec in self:
            rec.amendment_count = len(rec.amendment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('top.fleet.trip') or _('New')
        records = super().create(vals_list)
        for rec in records:
            if not rec.planned_distance:
                rec._calculate_route_distance()
        return records

    # -------------------------------------------------------------------------
    # WORKFLOW ACTIONS
    # -------------------------------------------------------------------------
    def action_view_on_map(self):
        self.ensure_one()
        return self.vehicle_id.action_view_on_map()

    def action_confirm(self):
        for trip in self:
            if trip.state != 'draft':
                raise UserError(_("Only draft trips can be confirmed."))
            v_ok, v_msg = trip.vehicle_id.check_availability(trip.planned_departure, trip.planned_arrival, exclude_trip_id=trip.id)
            if not v_ok:
                raise UserError(v_msg)
            d_ok, d_msg = trip.driver_id.check_availability(trip.planned_departure, trip.planned_arrival, exclude_trip_id=trip.id)
            if not d_ok:
                raise UserError(d_msg)

            trip.write({'state': 'ready'})
            trip.vehicle_id.write({'operational_status': 'assigned'})
            trip.driver_id.write({'driver_status': 'assigned'})
            trip.message_post(body=_("Trip confirmed and marked as ready for dispatch."))

    def action_dispatch(self):
        """Directly dispatch the trip to 'Dispatched' state without the inspection wizard.
        Vehicle inspections are performed separately via the Vehicle Inspections menu."""
        for trip in self:
            if trip.state != 'ready':
                raise UserError(_("Only trips in 'Ready' state can be dispatched."))
            now = fields.Datetime.now()
            write_vals = {
                'state': 'dispatched',
                'dispatch_date': now,
                'dispatched_by_id': self.env.user.id,
            }
            if not trip.planned_distance:
                trip._calculate_route_distance()
            if not trip.initial_planned_distance and trip.planned_distance:
                write_vals['initial_planned_distance'] = trip.planned_distance
            trip.write(write_vals)
            trip.vehicle_id.write({'operational_status': 'on_trip'})
            trip.driver_id.write({'driver_status': 'on_trip'})
            if trip.backup_driver_id:
                trip.backup_driver_id.write({'driver_status': 'on_trip'})
            for req in (trip.request_ids | trip.request_id):
                req_vals = {}
                if req and req.state not in ('dispatched', 'in_transit', 'completed', 'closed'):
                    req_vals['state'] = 'dispatched'
                if not req.initial_estimated_distance and req.estimated_distance:
                    req_vals['initial_estimated_distance'] = req.estimated_distance
                if req_vals:
                    req.write(req_vals)
            trip.message_post(body=_("Trip dispatched. Vehicle is en route."))

    def action_add_enroute_stop(self):
        """Opens quick wizard to add an intermediate stop while dispatched or in transit."""
        self.ensure_one()
        return {
            'name': _('Add En-Route Stop & Update Route'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.enroute.stop.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id,
            }
        }

    def action_open_dispatch_wizard(self):
        self.ensure_one()
        live_fuel = self.vehicle_id.live_fuel_level or (self.vehicle_id.gps_device_id and self.vehicle_id.gps_device_id.fuel_level) or 0.0
        return {
            'name': _('Pre-Dispatch Inspection Checklist (Section 35)'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.dispatch.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id,
                'default_start_odometer': self.vehicle_id.gps_device_id.odometer or self.vehicle_id.odometer or 0.0,
                'default_start_fuel': live_fuel,
            }
        }

    def action_open_return_wizard(self):
        """Opens Post-Trip Return Checklist Wizard (Section 36)."""
        self.ensure_one()
        end_odo = self.gps_device_id.odometer if (self.gps_device_id and self.gps_device_id.odometer) else (self.start_odometer or 0.0)
        live_fuel = self.vehicle_id.live_fuel_level or (self.vehicle_id.gps_device_id and self.vehicle_id.gps_device_id.fuel_level) or 0.0
        return {
            'name': _('Post-Trip Return Inspection Checklist (Section 36)'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.trip.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id,
                'default_end_odometer': end_odo,
                'default_end_fuel': live_fuel,
            }
        }

    def action_in_transit(self):
        for trip in self:
            if trip.state != 'dispatched':
                raise UserError(_("Trip must be dispatched before moving to in-transit status."))
            trip.write({'state': 'in_transit'})
            if trip.request_id and trip.request_id.state != 'in_transit':
                trip.request_id.write({'state': 'in_transit'})
            for req in trip.request_ids:
                if req.state != 'in_transit':
                    req.write({'state': 'in_transit'})
            trip.message_post(body=_("Vehicle is actively in transit."))

    def action_attach_transport_request(self, request_id):
        """Attaches an additional transport request to this trip, creating corresponding stops."""
        self.ensure_one()
        req = self.env['top.transport.request'].browse(request_id)
        if not req.exists():
            raise UserError(_("Transport request not found."))
        
        self.request_ids = [(4, req.id)]
        req.write({
            'trip_id': self.id,
            'assigned_vehicle_id': self.vehicle_id.id,
            'assigned_driver_id': self.driver_id.id,
            'state': 'assigned' if self.state in ['draft', 'ready'] else 'in_transit',
        })
        
        # Add stops for the request's origin and destination or its intermediate stops
        seq = (max(self.waypoint_ids.mapped('sequence')) + 10) if self.waypoint_ids else 10
        if req.stop_ids:
            for st in req.stop_ids:
                self.env['top.fleet.trip.waypoint'].create({
                    'trip_id': self.id,
                    'sequence': seq,
                    'location_id': st.location_id.id if st.location_id else False,
                    'location_name': st.location_name,
                    'stop_type': st.stop_type,
                    'request_id': req.id,
                    'cargo_or_passenger_notes': st.cargo_or_passenger_notes,
                    'notes': st.notes,
                    'state': 'pending',
                })
                seq += 10
        else:
            self.env['top.fleet.trip.waypoint'].create({
                'trip_id': self.id,
                'sequence': seq,
                'location_id': req.origin_location_id.id if req.origin_location_id else False,
                'location_name': req.origin,
                'stop_type': 'pickup',
                'request_id': req.id,
                'cargo_or_passenger_notes': req.cargo_description or (_("%s Passengers") % req.passenger_count),
                'state': 'pending',
            })
            self.env['top.fleet.trip.waypoint'].create({
                'trip_id': self.id,
                'sequence': seq + 10,
                'location_id': req.destination_location_id.id if req.destination_location_id else False,
                'location_name': req.destination,
                'stop_type': 'delivery',
                'request_id': req.id,
                'cargo_or_passenger_notes': req.cargo_description or (_("%s Passengers") % req.passenger_count),
                'state': 'pending',
            })
        
        self.message_post(
            body=_("Consolidated additional Transport Request <strong>%s</strong> into this trip. Pickup & delivery waypoints appended.") % req.name
        )
        req.message_post(
            body=_("Attached to consolidated Trip <a href='#' data-oe-model='top.fleet.trip' data-oe-id='%s'>%s</a>.") % (self.id, self.name)
        )

    def action_reconcile(self):
        for trip in self:
            if trip.state != 'completed':
                raise UserError(_("Only completed trips can be reconciled."))
            trip.write({'state': 'reconciled'})
            if trip.request_id and trip.request_id.state != 'reconciled':
                trip.request_id.write({'state': 'reconciled'})
            trip.message_post(
                body=_("<strong>Trip Reconciled (Section 29)</strong><br/>Distance Variance: %s km<br/>Duration Variance: %s hrs<br/>Fuel Variance: %s L<br/>Consumption Rate: %s L/100km") % (
                    trip.variance_distance, trip.variance_duration, trip.variance_fuel, trip.fuel_consumption_rate
                )
            )

    def action_close(self):
        for trip in self:
            if trip.state != 'reconciled':
                raise UserError(_("Only reconciled trips can be closed."))
            trip.write({'state': 'closed'})
            if trip.request_id and trip.request_id.state != 'closed':
                trip.request_id.write({'state': 'closed'})
            trip.message_post(body=_("Trip successfully closed."))

    def action_cancel(self):
        for trip in self:
            if trip.state in ['in_transit', 'completed', 'reconciled', 'closed']:
                raise UserError(_("Cannot cancel a trip that is in transit or completed."))
            trip.write({'state': 'cancelled'})
            trip.vehicle_id.write({'operational_status': 'available'})
            trip.driver_id.write({'driver_status': 'available'})
            if trip.request_id and trip.request_id.state != 'cancelled':
                trip.request_id.write({'state': 'approved'})
            trip.message_post(body=_("Trip cancelled."))

    # -------------------------------------------------------------------------
    # MOBILE & NOTIFICATION ACTIONS (Sections 50 & 51)
    # -------------------------------------------------------------------------
    def action_record_fuel(self):
        """Section 51 Mobile: Quickly record fuel consumption/receipt from trip."""
        self.ensure_one()
        return {
            'name': _('Record Fuel Consumption (Section 30 & 51)'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.fuel.log',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_trip_id': self.id,
                'default_vehicle_id': self.vehicle_id.id,
                'default_driver_id': self.driver_id.id,
                'default_odometer': self.vehicle_id.odometer or self.start_odometer or 0.0,
            }
        }

    def action_report_accident(self):
        """Section 51 Mobile: Report incident/accident and upload photo directly from trip."""
        self.ensure_one()
        return {
            'name': _('Report Incident / Damage (Section 34 & 51)'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.accident',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_trip_id': self.id,
                'default_vehicle_id': self.vehicle_id.id,
                'default_driver_id': self.driver_id.id,
                'default_location': self.current_address or self.destination,
                'default_latitude': self.current_latitude,
                'default_longitude': self.current_longitude,
            }
        }

    @api.model
    def cron_check_trip_delays(self):
        """Section 50: Periodic scan for in-transit trips that have passed planned arrival."""
        now = fields.Datetime.now()
        delayed_trips = self.search([
            ('state', '=', 'in_transit'),
            ('planned_arrival', '<', now),
        ])
        officer_group = self.env.ref('elmi_logistics_fleet.group_fleet_officer', raise_if_not_found=False)
        officer_users = (officer_group.user_ids or officer_group.all_user_ids) if officer_group else False
        officer_user = officer_users[0] if officer_users else self.env.user
        activity_type = self.env.ref('elmi_logistics_fleet.mail_act_trip_delay', raise_if_not_found=False)
        template = self.env.ref('elmi_logistics_fleet.mail_template_trip_delay', raise_if_not_found=False)

        for trip in delayed_trips:
            if activity_type:
                existing = self.env['mail.activity'].search([
                    ('res_model', '=', 'top.fleet.trip'),
                    ('res_id', '=', trip.id),
                    ('activity_type_id', '=', activity_type.id),
                ], limit=1)
                if not existing:
                    trip.activity_schedule(
                        'elmi_logistics_fleet.mail_act_trip_delay',
                        summary=_("Trip Delay Detected: %s past planned arrival (%s)") % (trip.name, trip.planned_arrival),
                        user_id=officer_user.id,
                    )
                    if template:
                        template.send_mail(trip.id, force_send=False)

    def get_sub_trips_details(self):
        """Returns ordered sub-trips/legs breakdown with travel duration, dwell times, and status."""
        self.ensure_one()
        legs = []
        waypoints = self.waypoint_ids.sorted(key=lambda w: (w.sequence, w.id))
        
        prev_loc = self.origin or _("Origin")
        prev_dep = self.actual_departure or self.planned_departure
        leg_num = 1

        for wp in waypoints:
            arr_time = wp.actual_arrival or wp.estimated_arrival
            dep_time = wp.actual_departure or arr_time
            
            # Travel duration between departure from previous point and arrival at this stop
            duration_secs = (arr_time - prev_dep).total_seconds() if (arr_time and prev_dep and arr_time >= prev_dep) else 0.0
            dur_hours = round(duration_secs / 3600.0, 2)
            hrs = int(dur_hours)
            mins = int(round((dur_hours - hrs) * 60))
            dur_display = f"{hrs}h {mins}m" if dur_hours > 0 else "0h 0m"
            
            # Dwell time
            dwell_hours = wp.time_spent_hours or 0.0
            d_hrs = int(dwell_hours)
            d_mins = int(round((dwell_hours - d_hrs) * 60))
            dwell_display = f"{d_hrs}h {d_mins}m" if dwell_hours > 0 else "0h 0m"
            
            stop_type_label = dict(wp._fields['stop_type'].selection).get(wp.stop_type, wp.stop_type) if 'stop_type' in wp._fields else wp.stop_type
            status_label = dict(wp._fields['state'].selection).get(wp.state, wp.state) if 'state' in wp._fields else wp.state

            legs.append({
                'leg_number': leg_num,
                'from_location': prev_loc,
                'to_location': wp.location_name or _("Waypoint Stop"),
                'departure_time': prev_dep,
                'arrival_time': arr_time,
                'travel_time_hours': dur_hours,
                'travel_time_display': dur_display,
                'dwell_time_hours': dwell_hours,
                'dwell_time_display': dwell_display,
                'stop_type': wp.stop_type,
                'stop_type_label': stop_type_label,
                'status': status_label,
                'notes': wp.cargo_or_passenger_notes or wp.notes or '',
                'odometer': wp.odometer or 0.0,
            })
            prev_loc = wp.location_name or prev_loc
            prev_dep = dep_time or prev_dep
            leg_num += 1

        # Final Leg to destination
        final_arr = self.actual_arrival or self.planned_arrival
        duration_secs = (final_arr - prev_dep).total_seconds() if (final_arr and prev_dep and final_arr >= prev_dep) else 0.0
        dur_hours = round(duration_secs / 3600.0, 2)
        hrs = int(dur_hours)
        mins = int(round((dur_hours - hrs) * 60))
        dur_display = f"{hrs}h {mins}m" if dur_hours > 0 else "0h 0m"

        state_label = dict(self._fields['state'].selection).get(self.state, self.state)
        legs.append({
            'leg_number': leg_num,
            'from_location': prev_loc,
            'to_location': self.destination or _("Final Destination"),
            'departure_time': prev_dep,
            'arrival_time': final_arr,
            'travel_time_hours': dur_hours,
            'travel_time_display': dur_display,
            'dwell_time_hours': 0.0,
            'dwell_time_display': "-",
            'stop_type': 'destination',
            'stop_type_label': _("Final Return / Destination Arrival"),
            'status': _("Completed") if self.state == 'completed' else state_label,
            'notes': self.purpose or '',
            'odometer': self.end_odometer or 0.0,
        })
        return legs

    def get_fuel_summary(self):
        """Returns complete fuel metrics from first dispatch to final return."""
        self.ensure_one()
        start_f = self.start_fuel or 0.0
        refueled = self.total_refueled or 0.0
        gross_f = round(start_f + refueled, 2)
        end_f = self.end_fuel or self.current_fuel or 0.0
        consumed = self.actual_fuel or 0.0
        dist = self.actual_distance or 0.0
        rate = self.fuel_consumption_rate or 0.0
        kml = self.fuel_economy_kml or (round(dist / consumed, 2) if (dist > 0 and consumed > 0) else 0.0)
        method_label = dict(self._fields['fuel_consumption_method'].selection).get(self.fuel_consumption_method, 'Benchmark Norm')

        return {
            'start_odometer': self.start_odometer or 0.0,
            'end_odometer': self.end_odometer or 0.0,
            'total_distance': dist,
            'start_fuel': start_f,
            'total_refueled': refueled,
            'gross_fuel': gross_f,
            'end_fuel': end_f,
            'net_fuel_consumed': consumed,
            'expected_fuel': self.expected_fuel or 0.0,
            'variance_fuel': self.variance_fuel or 0.0,
            'fuel_rate_l100km': rate,
            'fuel_economy_kml': kml,
            'cost_per_km': self.cost_per_km or 0.0,
            'total_cost': self.total_trip_cost or 0.0,
            'theft_suspected': self.fuel_theft_suspected,
            'method': method_label,
        }

    def action_print_fleet_activity_report(self):
        """Prints the executive Fleet Activity, Sub-Trips & Fuel Report PDF."""
        return self.env.ref('elmi_logistics_fleet.action_report_fleet_activity').report_action(self)


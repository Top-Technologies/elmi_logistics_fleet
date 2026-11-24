# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class FleetTripWaypoint(models.Model):
    _name = 'top.fleet.trip.waypoint'
    _description = 'Fleet Trip Waypoint / Intermediate Stop'
    _order = 'trip_id, sequence, id'

    trip_id = fields.Many2one(
        'top.fleet.trip',
        string='Trip',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Stop Order', default=10)
    location_id = fields.Many2one(
        'top.logistics.location',
        string='Predefined Location',
    )
    location_name = fields.Char(string='Location / Stop Name', required=True)
    stop_type = fields.Selection([
        ('pickup', 'Passenger / Cargo Pickup'),
        ('delivery', 'Dropoff / Delivery'),
        ('waypoint', 'Intermediate Transit Stop'),
        ('rest', 'Rest / Fuel Stop'),
    ], string='Stop Purpose', default='waypoint', required=True)

    request_id = fields.Many2one(
        'top.transport.request',
        string='Linked Request',
        help='Specific transport request this stop belongs to if part of a consolidated multi-request order.',
    )
    cargo_or_passenger_notes = fields.Char(string='Passenger / Cargo Details')
    estimated_arrival = fields.Datetime(string='Estimated Arrival')
    actual_arrival = fields.Datetime(string='Actual Arrival')
    actual_departure = fields.Datetime(string='Actual Departure')
    odometer = fields.Float(string='Odometer at Stop (km)')
    vehicle_id = fields.Many2one('fleet.vehicle', related='trip_id.vehicle_id', store=True, string='Vehicle')
    driver_id = fields.Many2one('hr.employee', related='trip_id.driver_id', store=True, string='Driver')
    trip_date = fields.Datetime(related='trip_id.actual_departure', store=True, string='Trip Date')
    trip_state = fields.Selection(related='trip_id.state', store=True, string='Trip State')

    from_location_name = fields.Char(string='From Point / Origin', compute='_compute_leg_metrics', store=True, compute_sudo=True)
    travel_time_hours = fields.Float(string='Travel Time (Hours)', compute='_compute_leg_metrics', store=True, compute_sudo=True)
    travel_time_display = fields.Char(string='Travel Duration', compute='_compute_leg_metrics', store=True, compute_sudo=True)
    dwell_time_display = fields.Char(string='Dwell Duration', compute='_compute_time_spent', store=True)

    time_spent_hours = fields.Float(
        string='Time Spent / Dwell (Hours)',
        compute='_compute_time_spent',
        store=True,
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('completed', 'Completed / Visited'),
        ('cancelled', 'Cancelled / Skipped'),
    ], string='Stop Status', default='pending')
    completed = fields.Boolean(
        string='Stop Visited',
        compute='_compute_completed',
        store=True,
        readonly=False,
    )
    notes = fields.Char(string='Instructions / Activity')

    @api.onchange('location_id')
    def _onchange_location_id(self):
        if self.location_id and not self.location_name:
            self.location_name = self.location_id.display_name or self.location_id.name

    @api.depends('state')
    def _compute_completed(self):
        for rec in self:
            rec.completed = (rec.state == 'completed')

    @api.onchange('completed')
    def _onchange_completed(self):
        for rec in self:
            if rec.completed and rec.state != 'completed':
                rec.state = 'completed'
                if not rec.actual_arrival:
                    rec.actual_arrival = fields.Datetime.now()
            elif not rec.completed and rec.state == 'completed':
                rec.state = 'pending'

    @api.depends('actual_arrival', 'actual_departure')
    def _compute_time_spent(self):
        for rec in self:
            if rec.actual_arrival and rec.actual_departure and rec.actual_departure > rec.actual_arrival:
                delta = rec.actual_departure - rec.actual_arrival
                rec.time_spent_hours = round(delta.total_seconds() / 3600.0, 2)
            else:
                rec.time_spent_hours = 0.0

            if rec.time_spent_hours > 0.0:
                hrs = int(rec.time_spent_hours)
                mins = int(round((rec.time_spent_hours - hrs) * 60))
                rec.dwell_time_display = f"{hrs}h {mins}m"
            else:
                rec.dwell_time_display = "0h 0m"

    @api.depends('trip_id', 'trip_id.waypoint_ids', 'trip_id.origin', 'trip_id.actual_departure', 'trip_id.planned_departure', 'actual_arrival', 'estimated_arrival')
    def _compute_leg_metrics(self):
        for rec in self:
            if not rec.trip_id:
                rec.from_location_name = False
                rec.travel_time_hours = 0.0
                rec.travel_time_display = "0h 0m"
                continue

            trip = rec.trip_id
            sorted_wps = trip.waypoint_ids.sorted(key=lambda w: (w.sequence, w.id))
            idx = False
            for i, wp in enumerate(sorted_wps):
                if wp.id == rec.id:
                    idx = i
                    break

            if idx is False or idx == 0:
                from_loc = trip.origin or _("Origin")
                prev_dep = trip.actual_departure or trip.planned_departure
            else:
                prev_wp = sorted_wps[idx - 1]
                from_loc = prev_wp.location_name or _("Waypoint")
                prev_dep = prev_wp.actual_departure or prev_wp.actual_arrival

            rec.from_location_name = from_loc
            arr = rec.actual_arrival or rec.estimated_arrival
            if arr and prev_dep and arr >= prev_dep:
                delta_secs = (arr - prev_dep).total_seconds()
                hours = round(delta_secs / 3600.0, 2)
                rec.travel_time_hours = hours
                h = int(hours)
                m = int(round((hours - h) * 60))
                rec.travel_time_display = f"{h}h {m}m"
            else:
                rec.travel_time_hours = 0.0
                rec.travel_time_display = "0h 0m"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('location_name') and vals.get('location_id'):
                loc = self.env['top.logistics.location'].browse(vals['location_id'])
                if loc:
                    vals['location_name'] = loc.name or loc.display_name or ''
        records = super().create(vals_list)
        for rec in records:
            trip = rec.trip_id
            if not trip:
                continue

            # Auto-link request_id from trip if not explicitly set
            req = rec.request_id or trip.request_id
            if req and not rec.request_id:
                rec.request_id = req.id

            # Sync stop to linked Transport Request if not present
            if req:
                existing_stop = req.stop_ids.filtered(
                    lambda s: s.location_name == rec.location_name or (s.location_id and rec.location_id and s.location_id == rec.location_id)
                )
                if not existing_stop:
                    self.env['top.transport.request.stop'].create({
                        'request_id': req.id,
                        'sequence': rec.sequence,
                        'location_id': rec.location_id.id if rec.location_id else False,
                        'location_name': rec.location_name,
                        'stop_type': rec.stop_type,
                        'cargo_or_passenger_notes': rec.cargo_or_passenger_notes,
                        'estimated_arrival': rec.estimated_arrival,
                        'state': rec.state or 'pending',
                        'notes': rec.notes or _("Added en-route during trip %s") % trip.name,
                    })

            # Recalculate route metrics
            old_distance = trip.planned_distance or 0.0
            trip._calculate_route_distance()
            new_distance = trip.planned_distance or 0.0

            # If trip was already dispatched or in transit, track the distance difference
            if trip.state in ['dispatched', 'in_transit']:
                if not trip.initial_planned_distance and old_distance > 0.0:
                    trip.initial_planned_distance = old_distance

                diff = round(new_distance - old_distance, 1)
                if diff > 0.0:
                    trip.enroute_distance_added = round((trip.enroute_distance_added or 0.0) + diff, 1)

                if req:
                    if not req.initial_estimated_distance and old_distance > 0.0:
                        req.initial_estimated_distance = old_distance
                    if diff > 0.0:
                        req.enroute_distance_added = round((req.enroute_distance_added or 0.0) + diff, 1)
                    req.estimated_distance = new_distance
                    req.estimated_duration = trip.planned_duration

                    # Chatter audit logs on both records
                    diff_sign = f"+{diff}" if diff >= 0 else f"{diff}"
                    trip.message_post(body=_(
                        "📍 <b>En-Route Intermediate Stop Added:</b> %s (%s)<br/>"
                        "• Added Route Distance: <b>%s km</b><br/>"
                        "• Revised Total Distance: <b>%0.1f km</b><br/>"
                        "• Synchronized to Transport Request: <b>%s</b>"
                    ) % (
                        rec.location_name,
                        dict(rec._fields['stop_type'].selection).get(rec.stop_type, rec.stop_type),
                        diff_sign, new_distance, req.name
                    ))
                    req.message_post(body=_(
                        "📍 <b>En-Route Stop Added from Trip %s:</b> %s (%s)<br/>"
                        "• Additional Distance Added: <b>%s km</b><br/>"
                        "• Revised Total Request Distance: <b>%0.1f km</b>"
                    ) % (
                        trip.name, rec.location_name,
                        dict(rec._fields['stop_type'].selection).get(rec.stop_type, rec.stop_type),
                        diff_sign, new_distance
                    ))
        return records

    def unlink(self):
        trips = self.mapped('trip_id')
        res = super().unlink()
        for trip in trips:
            if trip.exists():
                trip._calculate_route_distance()
        return res

    def action_mark_completed(self):
        now = fields.Datetime.now()
        for rec in self:
            vals = {'state': 'completed', 'completed': True}
            if not rec.actual_arrival:
                vals['actual_arrival'] = now
            if not rec.actual_departure:
                vals['actual_departure'] = now
            rec.write(vals)

            if rec.request_id:
                matching = rec.request_id.stop_ids.filtered(
                    lambda s: s.location_name == rec.location_name or (s.location_id and rec.location_id and s.location_id == rec.location_id)
                )
                if matching:
                    matching.write({'state': 'completed', 'completed': True, 'actual_arrival': now, 'actual_departure': now})

    def action_cancel_stop(self):
        for rec in self:
            rec.write({'state': 'cancelled', 'completed': False})
            if rec.request_id:
                matching = rec.request_id.stop_ids.filtered(
                    lambda s: s.location_name == rec.location_name or (s.location_id and rec.location_id and s.location_id == rec.location_id)
                )
                if matching:
                    matching.write({'state': 'cancelled', 'completed': False})

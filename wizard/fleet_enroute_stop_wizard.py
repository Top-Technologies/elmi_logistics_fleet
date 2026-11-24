# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FleetEnrouteStopWizard(models.TransientModel):
    _name = 'top.fleet.enroute.stop.wizard'
    _description = 'Add En-Route Intermediate Stop / Sub-Trip'

    trip_id = fields.Many2one(
        'top.fleet.trip',
        string='Trip',
        required=True,
    )
    request_id = fields.Many2one(
        'top.transport.request',
        string='Linked Transport Request',
        related='trip_id.request_id',
    )
    location_id = fields.Many2one(
        'top.logistics.location',
        string='Predefined Location',
        help='Select an existing predefined warehouse, branch, farm, or customer location.',
    )
    location_name = fields.Char(
        string='Location / Stop Name',
        required=True,
    )
    stop_type = fields.Selection([
        ('pickup', 'Passenger / Cargo Pickup'),
        ('delivery', 'Dropoff / Delivery'),
        ('waypoint', 'Intermediate Transit Stop'),
        ('rest', 'Rest / Fuel Stop'),
    ], string='Stop Purpose', default='waypoint', required=True)

    cargo_or_passenger_notes = fields.Char(string='Passengers / Cargo Details')
    estimated_arrival = fields.Datetime(string='Estimated Arrival')
    notes = fields.Char(
        string='Reason / Instructions',
        help='State reason for adding stop while in transit (e.g. emergency cargo pickup, client detour, route diversion).',
    )

    current_planned_distance = fields.Float(
        string='Current Planned Distance (km)',
        related='trip_id.planned_distance',
    )
    projected_new_distance = fields.Float(
        string='Projected New Distance (km)',
        compute='_compute_projected_metrics',
    )
    distance_difference = fields.Float(
        string='Additional Distance (+km)',
        compute='_compute_projected_metrics',
    )

    @api.onchange('location_id')
    def _onchange_location_id(self):
        if self.location_id:
            self.location_name = self.location_id.display_name or self.location_id.name

    @api.depends('trip_id', 'location_id')
    def _compute_projected_metrics(self):
        for wiz in self:
            trip = wiz.trip_id
            if not trip:
                wiz.projected_new_distance = 0.0
                wiz.distance_difference = 0.0
                continue

            current_dist = trip.planned_distance or 0.0

            # Gather current points + new stop point
            points = []
            if trip.origin_location_id and trip.origin_location_id.latitude and trip.origin_location_id.longitude:
                points.append((trip.origin_location_id.latitude, trip.origin_location_id.longitude))

            for wp in trip.waypoint_ids.sorted(key=lambda w: (w.sequence, w.id)):
                if wp.location_id and wp.location_id.latitude and wp.location_id.longitude:
                    points.append((wp.location_id.latitude, wp.location_id.longitude))

            # Add the new stop candidate
            if wiz.location_id and wiz.location_id.latitude and wiz.location_id.longitude:
                points.append((wiz.location_id.latitude, wiz.location_id.longitude))

            if trip.destination_location_id and trip.destination_location_id.latitude and trip.destination_location_id.longitude:
                points.append((trip.destination_location_id.latitude, trip.destination_location_id.longitude))

            if len(points) >= 2:
                metrics = self.env['top.logistics.location'].calculate_route_metrics(points)
                new_dist = metrics.get('distance_km', current_dist)
                wiz.projected_new_distance = new_dist
                wiz.distance_difference = round(max(0.0, new_dist - current_dist), 1)
            else:
                wiz.projected_new_distance = current_dist
                wiz.distance_difference = 0.0

    def action_add_stop(self):
        """Creates waypoint, syncs to transport request, and recalibrates route metrics."""
        self.ensure_one()
        trip = self.trip_id
        if not trip:
            raise UserError(_("No trip selected."))

        # Determine next sequence
        seq = 10
        if trip.waypoint_ids:
            seq = max(trip.waypoint_ids.mapped('sequence') or [0]) + 10

        waypoint_vals = {
            'trip_id': trip.id,
            'sequence': seq,
            'location_id': self.location_id.id if self.location_id else False,
            'location_name': self.location_name,
            'stop_type': self.stop_type,
            'request_id': trip.request_id.id if trip.request_id else False,
            'cargo_or_passenger_notes': self.cargo_or_passenger_notes,
            'estimated_arrival': self.estimated_arrival,
            'notes': self.notes or _("Added en-route"),
            'state': 'pending',
        }
        waypoint = self.env['top.fleet.trip.waypoint'].create(waypoint_vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("En-Route Stop Added"),
                'message': _("Stop '%s' added. Planned distance updated to %s km.") % (
                    waypoint.location_name, trip.planned_distance
                ),
                'type': 'success',
                'sticky': False,
            }
        }

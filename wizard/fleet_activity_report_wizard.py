# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FleetActivityReportWizard(models.TransientModel):
    _name = 'top.fleet.activity.report.wizard'
    _description = 'Fleet Activity, Sub-Trips & Fuel Consumption Report Wizard'

    report_type = fields.Selection([
        ('today', 'Today'),
        ('this_week', 'This Week'),
        ('this_month', 'This Month'),
        ('custom', 'Custom Date Range'),
    ], string='Reporting Period', default='this_month', required=True)

    date_from = fields.Datetime(
        string='Date From',
        required=True,
        default=lambda self: datetime.combine(fields.Date.context_today(self).replace(day=1), time.min)
    )
    date_to = fields.Datetime(
        string='Date To',
        required=True,
        default=fields.Datetime.now
    )

    vehicle_ids = fields.Many2many(
        'fleet.vehicle',
        string='Vehicles',
        help='Leave empty to include all fleet vehicles.',
    )
    driver_ids = fields.Many2many(
        'hr.employee',
        string='Drivers',
        help='Leave empty to include all drivers.',
    )
    trip_state = fields.Selection([
        ('all', 'All Trips (Completed, In-Transit, Dispatched)'),
        ('completed', 'Completed Trips Only'),
        ('in_transit', 'In-Transit Trips Only'),
    ], string='Trip Status Filter', default='all', required=True)

    trip_ids = fields.Many2many(
        'top.fleet.trip',
        string='Specific Trips',
        help='Optional: specify explicit trips to analyze.',
    )

    @api.onchange('report_type')
    def _onchange_report_type(self):
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        if self.report_type == 'today':
            self.date_from = datetime.combine(today, time.min)
            self.date_to = datetime.combine(today, time.max)
        elif self.report_type == 'this_week':
            start_week = today - timedelta(days=today.weekday())
            self.date_from = datetime.combine(start_week, time.min)
            self.date_to = now
        elif self.report_type == 'this_month':
            start_month = today.replace(day=1)
            self.date_from = datetime.combine(start_month, time.min)
            self.date_to = now
        elif self.report_type == 'custom':
            if not self.date_from:
                self.date_from = now - timedelta(days=30)
            if not self.date_to:
                self.date_to = now

    def _get_trips(self):
        if self.trip_ids:
            return self.trip_ids

        domain = []
        if self.date_from:
            domain.append(('actual_departure', '>=', self.date_from))
        if self.date_to:
            domain.append(('actual_departure', '<=', self.date_to))

        if self.vehicle_ids:
            domain.append(('vehicle_id', 'in', self.vehicle_ids.ids))
        if self.driver_ids:
            domain.append(('driver_id', 'in', self.driver_ids.ids))

        if self.trip_state == 'completed':
            domain.append(('state', '=', 'completed'))
        elif self.trip_state == 'in_transit':
            domain.append(('state', '=', 'in_transit'))
        else:
            domain.append(('state', 'in', ['dispatched', 'in_transit', 'reconciled', 'completed']))

        trips = self.env['top.fleet.trip'].search(domain, order='actual_departure desc, id desc')
        if not trips:
            # Fallback to planned departure if actual departure is not yet set
            domain_fallback = [d for d in domain if d[0] != 'actual_departure']
            if self.date_from:
                domain_fallback.append(('planned_departure', '>=', self.date_from))
            if self.date_to:
                domain_fallback.append(('planned_departure', '<=', self.date_to))
            trips = self.env['top.fleet.trip'].search(domain_fallback, order='planned_departure desc, id desc')

        return trips

    def action_print_pdf(self):
        """Generates the executive PDF Fleet Activity Report."""
        self.ensure_one()
        trips = self._get_trips()
        if not trips:
            raise UserError(_("No trips found matching the selected period and criteria."))
        return self.env.ref('elmi_logistics_fleet.action_report_fleet_activity').report_action(trips)

    def action_view_trips(self):
        """Opens interactive Pivot, Graph, and List views for the filtered trips."""
        self.ensure_one()
        trips = self._get_trips()
        return {
            'name': _('Fleet Activity & Trips Analysis'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.trip',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', trips.ids)],
            'context': {
                'search_default_group_by_vehicle': 1,
            },
        }

    def action_view_sub_trips(self):
        """Opens interactive sub-trips and waypoint stops list and pivot analysis."""
        self.ensure_one()
        trips = self._get_trips()
        return {
            'name': _('Sub-Trips & Waypoint Stops Analysis'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.trip.waypoint',
            'view_mode': 'list,pivot,form',
            'domain': [('trip_id', 'in', trips.ids)],
            'context': {
                'search_default_group_by_trip': 1,
            },
        }

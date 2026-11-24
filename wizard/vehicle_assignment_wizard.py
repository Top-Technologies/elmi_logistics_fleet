from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class VehicleAssignmentWizard(models.TransientModel):
    _name = 'top.vehicle.assignment.wizard'
    _description = 'Vehicle & Driver Assignment Wizard'

    request_id = fields.Many2one(
        'top.transport.request',
        string='Transport Request',
        required=True,
    )
    requester_id = fields.Many2one(related='request_id.requester_id', string='Requester', readonly=True)
    origin = fields.Char(related='request_id.origin', string='Origin', readonly=True)
    destination = fields.Char(related='request_id.destination', string='Destination', readonly=True)
    required_date = fields.Datetime(related='request_id.required_date', string='Required Date', readonly=True)
    return_date = fields.Datetime(related='request_id.return_date', string='Return Date', readonly=True)
    vehicle_type_id = fields.Many2one(related='request_id.vehicle_type_id', string='Requested Vehicle Type', readonly=True)

    fleet_order_type = fields.Selection(
        related='request_id.fleet_order_type',
        string='Fleet Order Type',
        readonly=True,
    )
    eligible_driver_ids = fields.Many2many(
        'hr.employee',
        compute='_compute_eligible_driver_ids',
        string='Eligible Drivers',
    )
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle to Assign',
        required=True,
        domain="[('operational_status', 'in', ['available', 'assigned']), ('has_document_expired', '=', False), ('has_inspection_passed', '=', True)]",
    )
    vehicle_status_info = fields.Char(string='Vehicle Status', readonly=True)
    vehicle_service_info = fields.Char(string='Maintenance & Service', readonly=True)
    vehicle_to_origin_distance = fields.Float(
        string='Live Distance to Pickup (km)',
        compute='_compute_vehicle_to_origin_distance',
        help='Current distance from vehicle GPS position to the request origin.'
    )

    driver_id = fields.Many2one(
        'hr.employee',
        string='Primary Driver',
        required=True,
        domain="[('id', 'in', eligible_driver_ids)]",
        help='Driver assigned to this trip. Auto-filled if vehicle has dedicated driver, or select from drivers with Job Position Driver.',
    )
    driver_status_info = fields.Char(string='Driver Status', readonly=True)
    driver_license_info = fields.Char(string='License & Compliance', readonly=True)

    backup_driver_id = fields.Many2one(
        'hr.employee',
        string='Backup Driver',
        domain="['|', ('job_id.name', 'ilike', 'driver'), ('job_title', 'ilike', 'driver')]",
        help='Optional backup driver selected from employees with Job Position Driver.',
    )
    trip_coordinator_id = fields.Many2one(
        'res.users',
        string='Trip Coordinator',
        default=lambda self: self.env.user,
    )
    trip_type_id = fields.Many2one(
        'top.fleet.trip.type',
        string='Trip Type',
    )
    planned_distance = fields.Float(string='Planned Distance (km)')
    planned_duration = fields.Float(string='Planned Duration (Hours)')
    special_instructions = fields.Text(string='Special Instructions')

    @api.depends('vehicle_id')
    def _compute_eligible_driver_ids(self):
        for wiz in self:
            if wiz.vehicle_id:
                dedicated = wiz.vehicle_id.get_assigned_driver()
                if dedicated:
                    wiz.eligible_driver_ids = dedicated
                    continue
            # If no dedicated driver attached to vehicle, list only employees with job driver
            drivers = self.env['hr.employee'].search([
                '|', ('job_id.name', 'ilike', 'driver'), ('job_title', 'ilike', 'driver')
            ])
            wiz.eligible_driver_ids = drivers

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if res.get('vehicle_id') and not res.get('driver_id'):
            v = self.env['fleet.vehicle'].browse(res['vehicle_id'])
            if v.exists():
                assigned_drv = v.get_assigned_driver()
                if assigned_drv:
                    res['driver_id'] = assigned_drv.id
        return res

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            # If any driver is assigned to the vehicle, bring them to the driver section
            assigned_drv = self.vehicle_id.get_assigned_driver()
            if assigned_drv:
                self.driver_id = assigned_drv.id
                self._onchange_driver_id()
                return {'domain': {'driver_id': [('id', '=', assigned_drv.id)]}}
            else:
                self.driver_id = False
                self.driver_status_info = _("No dedicated driver assigned. Please select a driver.")
                self.driver_license_info = False
                # Return dynamic domain of drivers with driver job position
                return {'domain': {'driver_id': ['|', ('job_id.name', 'ilike', 'driver'), ('job_title', 'ilike', 'driver')]}}

        if self.vehicle_id and self.request_id:
            ok, msg = self.vehicle_id.check_availability(
                self.request_id.required_date, self.request_id.return_date
            )
            self.vehicle_status_info = _("Available") if ok else msg
            service_parts = []
            if self.vehicle_id.last_service_date:
                service_parts.append(_("Last Service: %s") % self.vehicle_id.last_service_date)
            if self.vehicle_id.next_service_date:
                service_parts.append(_("Next Due: %s") % self.vehicle_id.next_service_date)
            if self.vehicle_id.is_service_due:
                service_parts.append(_("⚠️ SERVICE OVERDUE"))
            self.vehicle_service_info = " | ".join(service_parts) or _("Service records up to date")
            if (not self.planned_distance or self.planned_distance == 0.0) and self.request_id.estimated_distance:
                self.planned_distance = self.request_id.estimated_distance
            if (not self.planned_duration or self.planned_duration == 0.0) and self.request_id.estimated_duration:
                self.planned_duration = self.request_id.estimated_duration

    @api.depends('vehicle_id', 'vehicle_id.gps_device_id', 'request_id', 'request_id.origin_location_id')
    def _compute_vehicle_to_origin_distance(self):
        for wiz in self:
            if wiz.vehicle_id and wiz.vehicle_id.gps_device_id and wiz.request_id and wiz.request_id.origin_location_id:
                dev = wiz.vehicle_id.gps_device_id
                orig = wiz.request_id.origin_location_id
                if dev.latitude and dev.longitude and orig.latitude and orig.longitude:
                    wiz.vehicle_to_origin_distance = self.env['top.logistics.location'].calculate_distance_km(
                        dev.latitude, dev.longitude, orig.latitude, orig.longitude
                    )
                else:
                    wiz.vehicle_to_origin_distance = 0.0
            else:
                wiz.vehicle_to_origin_distance = 0.0

    @api.onchange('driver_id')
    def _onchange_driver_id(self):
        if self.driver_id and self.request_id:
            ok, msg = self.driver_id.check_availability(
                self.request_id.required_date, self.request_id.return_date
            )
            self.driver_status_info = _("Available") if ok else msg
            if self.driver_id.license_expiry_date:
                expired = self.driver_id.is_license_expired
                self.driver_license_info = (_("⚠️ Expired on %s") if expired else _("Valid until %s")) % self.driver_id.license_expiry_date
            elif self.driver_id.is_driver:
                self.driver_license_info = _("Registered Driver (No Expiry Date)")
            else:
                self.driver_license_info = _("Employee Selected (Standard)")
        elif not self.driver_id:
            self.driver_status_info = False
            self.driver_license_info = False

    def action_confirm_assignment(self):
        self.ensure_one()
        req = self.request_id

        # Section 12 Validation: Vehicle
        v_ok, v_msg = self.vehicle_id.check_availability(req.required_date, req.return_date)
        if not v_ok:
            raise ValidationError(_("Vehicle Assignment Error: %s") % v_msg)

        # Section 12 Validation: Driver
        d_ok, d_msg = self.driver_id.check_availability(req.required_date, req.return_date)
        if not d_ok:
            raise ValidationError(_("Driver Assignment Error: %s") % d_msg)

        # Check backup driver if selected
        if self.backup_driver_id:
            if self.backup_driver_id.id == self.driver_id.id:
                raise ValidationError(_("Primary driver and backup driver cannot be the same person."))
            b_ok, b_msg = self.backup_driver_id.check_availability(req.required_date, req.return_date)
            if not b_ok:
                raise ValidationError(_("Backup Driver Assignment Error: %s") % b_msg)

        # Emergency bypass handling (Section 9)
        post_trip = False
        if req.priority == 'emergency' and req.state in ['draft', 'submitted', 'under_review']:
            post_trip = True

        # Create Trip record (Section 14)
        trip_vals = {
            'request_id': req.id,
            'request_ids': [(4, req.id)],
            'fleet_order_type': req.fleet_order_type or 'light',
            'vehicle_id': self.vehicle_id.id,
            'driver_id': self.driver_id.id,
            'backup_driver_id': self.backup_driver_id.id if self.backup_driver_id else False,
            'trip_coordinator_id': self.trip_coordinator_id.id if self.trip_coordinator_id else self.env.user.id,
            'trip_type_id': self.trip_type_id.id if self.trip_type_id else False,
            'origin_location_id': req.origin_location_id.id if req.origin_location_id else False,
            'destination_location_id': req.destination_location_id.id if req.destination_location_id else False,
            'origin': req.origin,
            'destination': req.destination,
            'planned_departure': req.required_date,
            'planned_arrival': req.return_date,
            'planned_distance': self.planned_distance,
            'planned_duration': self.planned_duration,
            'purpose': req.purpose,
            'special_instructions': self.special_instructions,
            'state': 'ready',
        }
        trip = self.env['top.fleet.trip'].create(trip_vals)

        # Copy multi-stop waypoints from request to trip
        seq = 10
        if req.stop_ids:
            for st in req.stop_ids:
                self.env['top.fleet.trip.waypoint'].create({
                    'trip_id': trip.id,
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

        # Update Request status and metadata
        req_vals = {
            'assigned_vehicle_id': self.vehicle_id.id,
            'assigned_driver_id': self.driver_id.id,
            'trip_id': trip.id,
            'state': 'assigned',
            'post_trip_review_required': post_trip,
        }
        if req.state in ['draft', 'submitted', 'under_review']:
            req_vals['approved_by_id'] = self.env.user.id
            req_vals['approval_date'] = fields.Datetime.now()

        req.write(req_vals)

        # Update resource statuses
        self.vehicle_id.write({'operational_status': 'assigned'})
        self.driver_id.write({'driver_status': 'assigned'})
        if self.backup_driver_id:
            self.backup_driver_id.write({'driver_status': 'assigned'})

        req.message_post(
            body=_("Vehicle <strong>%s</strong> and Driver <strong>%s</strong> assigned. Trip generated: <a href='#' data-oe-model='top.fleet.trip' data-oe-id='%s'>%s</a>") % (
                self.vehicle_id.name, self.driver_id.name, trip.id, trip.name
            )
        )

        # Section 50: Send "Vehicle Assigned" notification
        template_assigned = self.env.ref('elmi_logistics_fleet.mail_template_vehicle_assigned', raise_if_not_found=False)
        if template_assigned:
            template_assigned.send_mail(req.id, force_send=False)

        activity_assigned = self.env.ref('elmi_logistics_fleet.mail_act_vehicle_assigned', raise_if_not_found=False)
        if activity_assigned and req.requester_id:
            req.activity_schedule(
                'elmi_logistics_fleet.mail_act_vehicle_assigned',
                summary=_("Vehicle %s and Driver %s Assigned to Request %s") % (self.vehicle_id.name, self.driver_id.name, req.name),
                user_id=req.requester_id.id,
            )

        return {
            'name': _('Trip Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.trip',
            'res_id': trip.id,
            'view_mode': 'form',
            'target': 'current',
        }

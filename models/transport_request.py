from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TransportRequest(models.Model):
    _name = 'top.transport.request'
    _description = 'Transport Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Request Number',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
    )
    requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Requester Employee',
        compute='_compute_employee_id',
        store=True,
        readonly=False,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        compute='_compute_department_id',
        store=True,
        readonly=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    request_date = fields.Datetime(
        string='Request Date',
        default=fields.Datetime.now,
        readonly=True,
    )
    request_type = fields.Selection([
        ('transport', 'TR_ — Goods & Equipment Transport'),
        ('machinery', 'MR_ — Machinery / Plant Deployment'),
        ('passenger', 'PR_ — Passenger Transport'),
    ], string='Requisition Category', default='transport', required=True, tracking=True)

    request_origin = fields.Selection([
        ('rc', 'RC_ — Requisition Coordinator (Offline/Email)'),
        ('or', 'OR_ — Online Department (Direct ERP)'),
        ('sr', 'SR_ — Self-Request (Fleet Manager)'),
        ('pc', 'PC_ — Procurement Coordinator'),
    ], string='Requisition Origin', default='or', required=True, tracking=True)

    # Document Template Integration Fields (Matching Transport Request Form)
    document_title = fields.Char(
        string='Document Title',
        default='Transport Request Form',
    )
    document_no = fields.Char(
        string='Document No',
        default='DOC-TR-001',
    )
    issue_no = fields.Char(
        string='Issue No',
        default='01',
    )
    page_no = fields.Char(
        string='Page No',
        default='1 of 1',
    )
    department_or_project = fields.Char(
        string='Transport Request by (Department/Project)',
        compute='_compute_department_or_project',
        store=True,
        readonly=False,
        tracking=True,
        help="e.g. PROJECT SITE - ROHA",
    )
    requester_position = fields.Char(
        string='Requester Position',
        compute='_compute_requester_position',
        store=True,
        readonly=False,
        tracking=True,
        help="e.g. PROJECT MANAGER",
    )
    reference_work_order_no = fields.Char(
        string='Reference Work Order No',
        copy=False,
        tracking=True,
        help="e.g. MDO_260726_001",
    )
    # Origin Breakdown Fields (Pick up Address)
    origin_description = fields.Char(string='Origin Description')
    origin_state = fields.Char(string='Origin State', default='ADDIS ABABA')
    origin_city = fields.Char(string='Origin City', default='ADDIS ABABA')
    origin_subcity = fields.Char(string='Origin KK / Sub-City', help="e.g. KIRKOS")
    origin_woreda = fields.Char(string='Origin Woreda', help="e.g. 04")
    # Destination Breakdown Fields (Drop off Address)
    destination_description = fields.Char(string='Destination Description')
    destination_state = fields.Char(string='Destination State', default='ADDIS ABABA')
    destination_city = fields.Char(string='Destination City', default='ADDIS ABABA')
    destination_subcity = fields.Char(string='Destination Kebele / Sub-City', help="e.g. KOLFE KERANEO")
    destination_woreda = fields.Char(string='Destination Woreda', help="e.g. 03")
    # Delivery Date & Signatures
    authorizer_id = fields.Many2one(
        'res.users',
        string='Authorizer',
        default=lambda self: self.env.user,
        tracking=True,
    )
    authorizer_name = fields.Char(
        string='Authorizer Name',
        compute='_compute_authorizer_name',
        store=True,
        readonly=False,
        tracking=True,
    )
    requester_signature = fields.Binary(string='Requester Signature', copy=False)
    authorizer_signature = fields.Binary(string='Authorizer Signature', copy=False)
    # Type of Goods to be Transported (Dual One2many Tables)
    machinery_line_ids = fields.One2many(
        'top.transport.request.machinery.line',
        'request_id',
        string='Machinery / Vehicle to Transport',
    )
    goods_line_ids = fields.One2many(
        'top.transport.request.goods.line',
        'request_id',
        string='Goods to Transport',
    )
    passenger_line_ids = fields.One2many(
        'top.transport.request.passenger.line',
        'request_id',
        string='Passenger Manifest',
    )
    required_date = fields.Datetime(
        string='Required Date',
        required=True,
        tracking=True,
    )
    return_date = fields.Datetime(
        string='Return Date',
        required=True,
        tracking=True,
    )
    purpose = fields.Text(
        string='Purpose',
        required=True,
    )
    trip_type_id = fields.Many2one(
        'top.transport.request.type',
        string='Trip Type',
        required=True,
        tracking=True,
    )
    fleet_order_type = fields.Selection([
        ('light', 'Light Fleet'),
        ('heavy', 'Heavy Fleet'),
    ], string='Fleet Order Type', default='light', required=True, tracking=True)
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
    origin = fields.Char(
        string='Origin',
        compute='_compute_origin',
        store=True,
        readonly=False,
    )
    destination = fields.Char(
        string='Destination',
        compute='_compute_destination',
        store=True,
        readonly=False,
    )
    estimated_distance = fields.Float(
        string='Estimated Route Distance (km)',
        compute='_compute_estimated_distance',
        store=True,
        readonly=False,
        help='Auto-calculated road distance between Origin and Destination based on coordinates.'
    )
    estimated_duration = fields.Float(
        string='Estimated Duration (Hours)',
        compute='_compute_estimated_distance',
        store=True,
        readonly=False,
    )
    initial_estimated_distance = fields.Float(
        string='Initial Estimated Distance (km)',
        copy=False,
        help='Original planned distance at time of request approval.',
    )
    enroute_distance_added = fields.Float(
        string='En-Route Distance Added (km)',
        default=0.0,
        copy=False,
        help='Additional distance resulting from en-route stops added after dispatch.',
    )
    total_revised_distance = fields.Float(
        string='Total Revised Distance (km)',
        compute='_compute_total_revised_distance',
        store=True,
        help='Total distance including original estimated distance plus any en-route deviations.',
    )
    stop_ids = fields.One2many(
        'top.transport.request.stop',
        'request_id',
        string='Stops / Waypoints',
    )
    total_stops_count = fields.Integer(
        string='Total Stops Planned',
        compute='_compute_stops_summary',
        store=True,
    )
    completed_stops_count = fields.Integer(
        string='Stops Completed',
        compute='_compute_stops_summary',
        store=True,
    )
    cancelled_stops_count = fields.Integer(
        string='Stops Cancelled',
        compute='_compute_stops_summary',
        store=True,
    )
    passenger_count = fields.Integer(
        string='Passenger Count',
        default=1,
    )
    cargo_required = fields.Boolean(
        string='Cargo Required',
        default=False,
    )
    cargo_description = fields.Text(
        string='Cargo Description',
    )
    priority = fields.Selection(
        [
            ('low', 'Low'),
            ('normal', 'Normal'),
            ('high', 'High'),
            ('emergency', 'Emergency'),
        ],
        string='Priority',
        default='normal',
        required=True,
        tracking=True,
    )
    vehicle_type_id = fields.Many2one(
        'fleet.vehicle.model.category',
        string='Vehicle Type',
        tracking=True,
    )
    driver_required = fields.Boolean(
        string='Driver Required',
        default=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('under_review', 'Under Review'),
            ('approved', 'Approved'),
            ('vehicle_search', 'Vehicle Search'),
            ('assigned', 'Assigned'),
            ('dispatched', 'Dispatched'),
            ('in_transit', 'In Transit'),
            ('completed', 'Completed'),
            ('reconciled', 'Reconciled'),
            ('closed', 'Closed'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        readonly=True,
        tracking=True,
        index=True,
        copy=False,
    )

    # Workflow & Approval Metadata (Section 9)
    reviewed_by_id = fields.Many2one(
        'res.users',
        string='Reviewed By',
        readonly=True,
        copy=False,
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        copy=False,
    )
    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True,
        copy=False,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True,
        copy=False,
    )
    post_trip_review_required = fields.Boolean(
        string='Post-Trip Review Required',
        default=False,
        help="Flagged when an emergency request bypasses standard approval for immediate assignment.",
    )

    # Assignment & Trip Linkage (Sections 10, 11, 14)
    assigned_vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Assigned Vehicle',
        readonly=True,
        tracking=True,
        copy=False,
    )
    assigned_driver_id = fields.Many2one(
        'hr.employee',
        string='Assigned Driver',
        readonly=True,
        tracking=True,
        copy=False,
    )
    trip_id = fields.Many2one(
        'top.fleet.trip',
        string='Trip Record',
        readonly=True,
        copy=False,
    )
    trip_count = fields.Integer(
        string='Trip Count',
        compute='_compute_trip_count',
    )
    vehicle_last_service_date = fields.Date(
        related='assigned_vehicle_id.last_service_date',
        string='Vehicle Last Service Date',
        readonly=True,
    )
    vehicle_next_service_date = fields.Date(
        related='assigned_vehicle_id.next_service_date',
        string='Vehicle Next Service Due',
        readonly=True,
    )
    vehicle_service_status = fields.Selection(
        related='assigned_vehicle_id.service_status',
        string='Vehicle Service Status',
        readonly=True,
    )
    vehicle_is_service_due = fields.Boolean(
        related='assigned_vehicle_id.is_service_due',
        string='Maintenance Service Due Alert',
        readonly=True,
    )
    driver_license_expiry_date = fields.Date(
        related='assigned_driver_id.license_expiry_date',
        string='Driver License Expiration',
        readonly=True,
    )
    driver_is_license_expired = fields.Boolean(
        related='assigned_driver_id.is_license_expired',
        string='Driver License Expired',
        readonly=True,
    )
    driver_license_compliance = fields.Char(
        related='assigned_driver_id.license_compliance_status',
        string='Driver License Status',
        readonly=True,
    )
    trip_actual_distance = fields.Float(
        related='trip_id.actual_distance',
        string='Actual Distance (km)',
        readonly=True,
    )
    trip_actual_duration = fields.Float(
        related='trip_id.actual_duration',
        string='Actual Duration (Hours)',
        readonly=True,
    )
    trip_duration_display = fields.Char(
        string='Trip Duration Taken',
        compute='_compute_trip_duration_display',
    )

    @api.onchange('origin_location_id')
    def _onchange_origin_location_id(self):
        if self.origin_location_id:
            loc = self.origin_location_id
            self.origin = loc.display_name or loc.name
            if not self.origin_description:
                self.origin_description = loc.name
            if loc.state_name:
                self.origin_state = loc.state_name
            elif loc.state_id:
                self.origin_state = loc.state_id.name
            if loc.city:
                self.origin_city = loc.city
            if loc.subcity:
                self.origin_subcity = loc.subcity
            if loc.woreda:
                self.origin_woreda = loc.woreda

    @api.onchange('destination_location_id')
    def _onchange_destination_location_id(self):
        if self.destination_location_id:
            loc = self.destination_location_id
            self.destination = loc.display_name or loc.name
            if not self.destination_description:
                self.destination_description = loc.name
            if loc.state_name:
                self.destination_state = loc.state_name
            elif loc.state_id:
                self.destination_state = loc.state_id.name
            if loc.city:
                self.destination_city = loc.city
            if loc.kebele or loc.subcity:
                self.destination_subcity = loc.kebele or loc.subcity
            if loc.woreda:
                self.destination_woreda = loc.woreda

    @api.depends('origin_description', 'origin_location_id', 'origin_city', 'origin_subcity')
    def _compute_origin(self):
        for rec in self:
            if not rec.origin:
                parts = [rec.origin_description, rec.origin_subcity, rec.origin_city]
                rec.origin = ", ".join([p for p in parts if p]) or (rec.origin_location_id.display_name if rec.origin_location_id else _('Origin'))

    @api.depends('destination_description', 'destination_location_id', 'destination_city', 'destination_subcity')
    def _compute_destination(self):
        for rec in self:
            if not rec.destination:
                parts = [rec.destination_description, rec.destination_subcity, rec.destination_city]
                rec.destination = ", ".join([p for p in parts if p]) or (rec.destination_location_id.display_name if rec.destination_location_id else _('Destination'))

    @api.depends('origin_location_id', 'destination_location_id', 'origin_location_id.latitude', 'origin_location_id.longitude', 'destination_location_id.latitude', 'destination_location_id.longitude')
    def _compute_estimated_distance(self):
        for req in self:
            if req.origin_location_id and req.destination_location_id:
                p1 = (req.origin_location_id.latitude, req.origin_location_id.longitude)
                p2 = (req.destination_location_id.latitude, req.destination_location_id.longitude)
                if p1[0] and p1[1] and p2[0] and p2[1]:
                    metrics = self.env['top.logistics.location'].calculate_route_metrics([p1, p2])
                    req.estimated_distance = metrics.get('distance_km', 0.0)
                    req.estimated_duration = metrics.get('duration_hours', 0.0)
                else:
                    if not req.estimated_distance:
                        req.estimated_distance = 0.0
                    if not req.estimated_duration:
                        req.estimated_duration = 0.0
            else:
                if not req.estimated_distance:
                    req.estimated_distance = 0.0
                if not req.estimated_duration:
                    req.estimated_duration = 0.0

    @api.depends('estimated_distance', 'enroute_distance_added', 'initial_estimated_distance')
    def _compute_total_revised_distance(self):
        for req in self:
            if req.enroute_distance_added > 0.0:
                base = req.initial_estimated_distance or req.estimated_distance or 0.0
                req.total_revised_distance = round(base + req.enroute_distance_added, 1)
            else:
                req.total_revised_distance = req.estimated_distance or 0.0

    @api.depends('department_id', 'employee_id')
    def _compute_department_or_project(self):
        for record in self:
            if not record.department_or_project:
                if record.department_id:
                    record.department_or_project = record.department_id.name
                elif record.employee_id and record.employee_id.department_id:
                    record.department_or_project = record.employee_id.department_id.name
                else:
                    record.department_or_project = ''

    @api.depends('employee_id')
    def _compute_requester_position(self):
        for record in self:
            if not record.requester_position:
                if record.employee_id and record.employee_id.job_title:
                    record.requester_position = record.employee_id.job_title
                elif record.employee_id and record.employee_id.job_id:
                    record.requester_position = record.employee_id.job_id.name
                else:
                    record.requester_position = ''

    @api.depends('authorizer_id')
    def _compute_authorizer_name(self):
        for record in self:
            if not record.authorizer_name:
                record.authorizer_name = record.authorizer_id.name if record.authorizer_id else ''

    @api.depends('stop_ids.state')
    def _compute_stops_summary(self):
        for record in self:
            record.total_stops_count = len(record.stop_ids)
            record.completed_stops_count = len(record.stop_ids.filtered(lambda s: s.state == 'completed'))
            record.cancelled_stops_count = len(record.stop_ids.filtered(lambda s: s.state == 'cancelled'))

    @api.depends('trip_id.actual_duration')
    def _compute_trip_duration_display(self):
        for record in self:
            if record.trip_id and record.trip_id.actual_duration:
                total_hours = record.trip_id.actual_duration
                hrs = int(total_hours)
                mins = int(round((total_hours - hrs) * 60))
                record.trip_duration_display = f"{hrs}h {mins}m"
            else:
                record.trip_duration_display = _("Not Recorded")

    @api.depends('trip_id')
    def _compute_trip_count(self):
        for record in self:
            record.trip_count = 1 if record.trip_id else 0

    @api.depends('requester_id')
    def _compute_employee_id(self):
        for record in self:
            employee = self.env['hr.employee'].search([
                ('user_id', '=', record.requester_id.id),
                ('company_id', '=', record.company_id.id),
            ], limit=1)
            record.employee_id = employee or False

    @api.depends('employee_id')
    def _compute_department_id(self):
        for record in self:
            if record.employee_id and record.employee_id.department_id:
                record.department_id = record.employee_id.department_id
            elif not record.department_id:
                record.department_id = False

    @api.constrains('required_date', 'return_date')
    def _check_dates(self):
        for record in self:
            if record.required_date and record.return_date and record.return_date < record.required_date:
                raise ValidationError(_("Return Date (%s) cannot be earlier than Required Date (%s).") % (
                    record.return_date, record.required_date
                ))

    @api.constrains('passenger_count')
    def _check_passenger_count(self):
        for record in self:
            if record.passenger_count < 0:
                raise ValidationError(_("Passenger Count cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                req_type = vals.get('request_type', 'transport')
                origin = vals.get('request_origin', 'or')
                type_prefix_map = {'transport': 'TR', 'machinery': 'MR', 'passenger': 'PR'}
                origin_prefix_map = {'rc': 'RC', 'or': 'OR', 'sr': 'SR', 'pc': 'PC'}

                type_prefix = type_prefix_map.get(req_type, 'TR')
                orig_prefix = origin_prefix_map.get(origin, 'OR')

                seq_code = 'top.transport.request'
                num = self.env['ir.sequence'].next_by_code(seq_code) or '00001'
                # Format: [TYPE]_[ORIGIN]_[SEQ] e.g. TR_OR_2026_00001 or TR_2026_00001
                vals['name'] = f"{type_prefix}_{orig_prefix}_{num}"
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # WORKFLOW ACTIONS
    # -------------------------------------------------------------------------
    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Only draft requests can be submitted."))
            record.write({'state': 'submitted'})
            if record.priority == 'emergency':
                record.message_post(
                    body=_("<strong>EMERGENCY Transport Request Submitted!</strong> Immediate Fleet assignment authorized with post-trip review."),
                    message_type='notification',
                )
            else:
                record.message_post(
                    body=_("Transport request submitted for approval."),
                    message_type='notification',
                )

            # Section 50: Send "Transport Request Submitted" notification
            template_submitted = self.env.ref('elmi_logistics_fleet.mail_template_transport_request_submitted', raise_if_not_found=False)
            if template_submitted:
                template_submitted.send_mail(record.id, force_send=False)

            # Section 50: Send "Transport Request Awaiting Approval" notification & schedule activity
            approver_user = False
            if record.department_id and record.department_id.manager_id and record.department_id.manager_id.user_id:
                approver_user = record.department_id.manager_id.user_id
            else:
                approver_group = self.env.ref('elmi_logistics_fleet.group_department_approver', raise_if_not_found=False)
                if approver_group:
                    users = approver_group.user_ids or approver_group.all_user_ids
                    if users:
                        approver_user = users[0]

            if approver_user:
                activity_type = self.env.ref('elmi_logistics_fleet.mail_act_request_awaiting_approval', raise_if_not_found=False)
                if activity_type:
                    record.activity_schedule(
                        'elmi_logistics_fleet.mail_act_request_awaiting_approval',
                        summary=_("Transport Request Awaiting Approval: %s") % record.name,
                        user_id=approver_user.id,
                    )
            
            template_awaiting = self.env.ref('elmi_logistics_fleet.mail_template_request_awaiting_approval', raise_if_not_found=False)
            if template_awaiting:
                template_awaiting.send_mail(record.id, force_send=False)

            # Also notify Fleet Supervisor
            supervisor_group = self.env.ref('elmi_logistics_fleet.group_fleet_supervisor', raise_if_not_found=False)
            supervisor_users = (supervisor_group.user_ids or supervisor_group.all_user_ids) if supervisor_group else False
            supervisor_user = supervisor_users[0] if supervisor_users else False
            if supervisor_user:
                activity_type = self.env.ref('elmi_logistics_fleet.mail_act_request_awaiting_approval', raise_if_not_found=False)
                if activity_type:
                    record.activity_schedule(
                        'elmi_logistics_fleet.mail_act_request_awaiting_approval',
                        summary=_("Transport Order Awaiting Fleet Supervisor Review: %s") % record.name,
                        user_id=supervisor_user.id,
                    )

    def action_review(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError(_("Only submitted requests can be put under review."))
            record.write({
                'state': 'under_review',
                'reviewed_by_id': self.env.user.id,
            })
            record.message_post(body=_("Request reviewed by %s.") % self.env.user.name)

    def action_approve(self):
        for record in self:
            if record.state not in ['submitted', 'under_review']:
                raise UserError(_("Request cannot be approved in its current state."))
            record.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })
            record.message_post(body=_("Transport request approved by %s.") % self.env.user.name)

    def action_vehicle_search(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_("Vehicle search can only be initiated for approved requests."))
            record.write({'state': 'vehicle_search'})

    def action_open_assignment_wizard(self):
        """Opens vehicle and driver assignment wizard (Section 11)."""
        self.ensure_one()
        # In emergency mode, allows direct assignment
        context = {
            'default_request_id': self.id,
            'default_planned_distance': self.estimated_distance or 0.0,
            'default_planned_duration': self.estimated_duration or 0.0,
        }
        return {
            'name': _('Assign Vehicle & Driver'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.vehicle.assignment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    def action_view_trip(self):
        """Smart button action to view the generated trip."""
        self.ensure_one()
        if not self.trip_id:
            raise UserError(_("No trip has been created for this request yet."))
        return {
            'name': _('Trip Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'top.fleet.trip',
            'res_id': self.trip_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        for record in self:
            if record.state in ['in_transit', 'completed', 'reconciled', 'closed']:
                raise UserError(_("Cannot cancel a request that is already in transit or completed."))
            if record.trip_id and record.trip_id.state not in ['cancelled', 'draft']:
                record.trip_id.action_cancel()
            record.write({'state': 'cancelled'})
            record.message_post(body=_("Transport request cancelled."))

    def action_reset_draft(self):
        for record in self:
            if record.state not in ['cancelled', 'rejected']:
                raise UserError(_("Only cancelled or rejected requests can be reset to draft."))
            record.write({
                'state': 'draft',
                'rejection_reason': False,
            })
            record.message_post(body=_("Request reset to draft."))


class TransportRequestStop(models.Model):
    _name = 'top.transport.request.stop'
    _description = 'Transport Request Intermediate Stop / Waypoint'
    _order = 'request_id, sequence, id'

    request_id = fields.Many2one(
        'top.transport.request',
        string='Transport Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
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
    estimated_arrival = fields.Datetime(string='Estimated Arrival')
    actual_arrival = fields.Datetime(string='Actual Arrival')
    actual_departure = fields.Datetime(string='Actual Departure')
    cargo_or_passenger_notes = fields.Char(string='Passengers / Cargo Details')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled / Skipped'),
    ], string='Stop Status', default='pending')
    completed = fields.Boolean(
        string='Stop Visited',
        compute='_compute_completed',
        store=True,
        readonly=False,
    )
    notes = fields.Char(string='Notes / Instructions')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('location_name') and vals.get('location_id'):
                loc = self.env['top.logistics.location'].browse(vals['location_id'])
                if loc:
                    vals['location_name'] = loc.name or loc.display_name or ''
        return super().create(vals_list)

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

    def action_mark_completed(self):
        now = fields.Datetime.now()
        for rec in self:
            vals = {'state': 'completed', 'completed': True}
            if not rec.actual_arrival:
                vals['actual_arrival'] = now
            if not rec.actual_departure:
                vals['actual_departure'] = now
            rec.write(vals)

    def action_cancel_stop(self):
        for rec in self:
            rec.write({'state': 'cancelled', 'completed': False})


class TransportRequestMachineryLine(models.Model):
    _name = 'top.transport.request.machinery.line'
    _description = 'Transport Request Machinery / Vehicle Line'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'top.transport.request',
        string='Transport Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    line_no = fields.Integer(string='No.', compute='_compute_line_no', store=True, readonly=False)
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle / Machine',
    )
    description = fields.Char(
        string='Machine/Vehicle Description',
        required=True,
    )
    plate_no = fields.Char(string='Plate No.')
    reason = fields.Char(string='Reason', default='Mobilization')

    @api.depends('sequence', 'request_id')
    def _compute_line_no(self):
        for record in self:
            if not record.line_no and record.request_id:
                lines = record.request_id.machinery_line_ids
                idx = 1
                for l in lines:
                    if l == record:
                        record.line_no = idx
                        break
                    idx += 1
            if not record.line_no:
                record.line_no = 1

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            desc_parts = [self.vehicle_id.model_id.name or '', self.vehicle_id.name or '']
            cleaned = " ".join([p for p in desc_parts if p]).strip()
            if not self.description and cleaned:
                self.description = cleaned
            if not self.plate_no and self.vehicle_id.license_plate:
                self.plate_no = self.vehicle_id.license_plate


class TransportRequestGoodsLine(models.Model):
    _name = 'top.transport.request.goods.line'
    _description = 'Transport Request Goods Line'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'top.transport.request',
        string='Transport Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    line_no = fields.Integer(string='No.', compute='_compute_line_no', store=True, readonly=False)
    product_id = fields.Many2one(
        'product.product',
        string='Item / Product',
    )
    description = fields.Char(
        string='Description',
        required=True,
    )
    unit = fields.Char(string='Unit', default='Pc')
    quantity = fields.Float(string='Quantity', default=1.0)

    @api.depends('sequence', 'request_id')
    def _compute_line_no(self):
        for record in self:
            if not record.line_no and record.request_id:
                lines = record.request_id.goods_line_ids
                idx = 1
                for l in lines:
                    if l == record:
                        record.line_no = idx
                        break
                    idx += 1
            if not record.line_no:
                record.line_no = 1

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.description:
                self.description = self.product_id.display_name
            if self.product_id.uom_id and not self.unit:
                self.unit = self.product_id.uom_id.name


class TransportRequestPassengerLine(models.Model):
    _name = 'top.transport.request.passenger.line'
    _description = 'Passenger Travel Manifest Line'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'top.transport.request',
        string='Transport Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    employee_id = fields.Many2one('hr.employee', string='Passenger / Employee', required=True)
    passenger_name = fields.Char(string='Full Name', compute='_compute_passenger_details', store=True, readonly=False)
    position = fields.Char(string='Job Position', compute='_compute_passenger_details', store=True, readonly=False)
    department_id = fields.Many2one('hr.department', string='Department', compute='_compute_passenger_details', store=True, readonly=False)
    contact_phone = fields.Char(string='Phone / Contact')
    travel_date = fields.Date(string='Travel Date')
    return_date = fields.Date(string='Return Date')
    duration_days = fields.Integer(string='Duration of Stay (Days)', default=1)
    requires_vehicle_at_destination = fields.Boolean(
        string='Vehicle Required During Stay',
        default=False,
        help='Checked if passenger requires dedicated transport while stationed at project site.',
    )
    notes = fields.Char(string='Stopovers / Special Instructions')

    @api.depends('employee_id')
    def _compute_passenger_details(self):
        for rec in self:
            if rec.employee_id:
                rec.passenger_name = rec.employee_id.name
                rec.position = rec.employee_id.job_title or (rec.employee_id.job_id.name if rec.employee_id.job_id else '')
                rec.department_id = rec.employee_id.department_id
                rec.contact_phone = rec.employee_id.mobile_phone or rec.employee_id.work_phone



from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MachineryDeploymentOrder(models.Model):
    _name = 'top.machinery.deployment.order'
    _description = 'Machinery and Vehicle Deployment Order (MDO)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='MDO Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    request_ids = fields.Many2many(
        'top.transport.request',
        'top_mdo_request_rel',
        'mdo_id',
        'request_id',
        string='Consolidated Machinery Requests (MR_)',
        domain="[('request_type', '=', 'machinery'), ('state', 'in', ['approved', 'assigned'])]",
        tracking=True,
    )
    request_count = fields.Integer(string='Request Count', compute='_compute_request_count')

    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Machinery / Asset Assigned',
        required=True,
        tracking=True,
    )
    operator_id = fields.Many2one(
        'hr.employee',
        string='Primary Operator / Driver',
        tracking=True,
    )
    assistant_id = fields.Many2one(
        'hr.employee',
        string='Assistant / Greaser',
        tracking=True,
    )

    is_individual_assignment = fields.Boolean(
        string='Individual Light-Vehicle Assignment',
        default=False,
        tracking=True,
        help='Dedicated company car assignment to a manager/engineer rather than site heavy plant.',
    )
    custodian_employee_id = fields.Many2one(
        'hr.employee',
        string='Assigned Custodian (Company Car)',
        tracking=True,
    )

    project_site_id = fields.Many2one(
        'top.logistics.location',
        string='Destination Project Site / Camp',
        required=True,
        tracking=True,
    )

    date_from = fields.Datetime(
        string='Deployment Start Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    date_to = fields.Datetime(
        string='Planned Return / End Date',
        required=True,
        tracking=True,
    )
    operating_task = fields.Text(string='Scope of Work / Planned Activity')

    meter_type = fields.Selection([
        ('hours', 'Operating Hours (Heavy Plant)'),
        ('km', 'Kilometers (Light Vehicle / Truck)'),
    ], string='Meter Metric', default='hours', required=True)

    initial_meter_reading = fields.Float(string='Departure Meter Reading', tracking=True)
    return_meter_reading = fields.Float(string='Return Meter Reading', tracking=True)
    total_operated_units = fields.Float(
        string='Total Units Operated',
        compute='_compute_total_operated_units',
        store=True,
    )

    # Handover records
    handover_ids = fields.One2many(
        'fleet.vehicle.handover',
        'mdo_id',
        string='Digital Handover / Return Logs',
    )
    handover_count = fields.Integer(compute='_compute_handover_count')

    # Deployment Extensions
    extension_ids = fields.One2many(
        'top.mdo.extension',
        'mdo_id',
        string='Deployment Period Extensions',
    )

    state = fields.Selection([
        ('draft', 'Draft Plan'),
        ('approved', 'Approved by Fleet Manager'),
        ('dispatched', 'Dispatched to Site'),
        ('in_progress', 'Operating on Site'),
        ('completed', 'Returned and Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    fuel_rule_note = fields.Char(
        string='Fuel Supply Policy',
        readonly=True,
        default='MDO Fuel Suppressed: Fuel supplied exclusively via Site Fuel Tankers.',
    )

    @api.depends('request_ids')
    def _compute_request_count(self):
        for rec in self:
            rec.request_count = len(rec.request_ids)

    @api.depends('handover_ids')
    def _compute_handover_count(self):
        for rec in self:
            rec.handover_count = len(rec.handover_ids)

    @api.depends('initial_meter_reading', 'return_meter_reading')
    def _compute_total_operated_units(self):
        for rec in self:
            if rec.return_meter_reading >= rec.initial_meter_reading:
                rec.total_operated_units = round(rec.return_meter_reading - rec.initial_meter_reading, 1)
            else:
                rec.total_operated_units = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('top.machinery.deployment.order') or _('New')
        return super().create(vals_list)

    def action_approve(self):
        for rec in self:
            rec.state = 'approved'
            # Mark requests as assigned
            rec.request_ids.write({'state': 'assigned'})

    def action_dispatch(self):
        for rec in self:
            rec.state = 'dispatched'
            rec.vehicle_id.write({'operational_status': 'on_trip'})
            rec.request_ids.write({'state': 'dispatched'})

    def action_return_close(self):
        for rec in self:
            rec.state = 'completed'
            rec.vehicle_id.write({'operational_status': 'available'})
            rec.request_ids.write({'state': 'completed'})

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('completed', 'cancelled'):
                raise UserError(_("Only completed or cancelled deployment orders can be reset to draft."))
            rec.state = 'draft'
            rec.vehicle_id.write({'operational_status': 'available'})
            if rec.request_ids:
                rec.request_ids.write({'state': 'approved'})


class MdoExtension(models.Model):
    _name = 'top.mdo.extension'
    _description = 'MDO Deployment Extension Log'
    _inherit = ['mail.thread']

    mdo_id = fields.Many2one(
        'top.machinery.deployment.order',
        string='Deployment Order',
        required=True,
        ondelete='cascade',
    )
    request_id = fields.Many2one(
        'top.transport.request',
        string='Extension Request',
        help='Requisition requesting the extension.',
    )
    previous_return_date = fields.Datetime(string='Previous End Date', required=True)
    extended_return_date = fields.Datetime(string='Extended End Date', required=True)
    reason = fields.Text(string='Reason for Extension', required=True)
    approved_by_id = fields.Many2one('res.users', string='Approved By', default=lambda self: self.env.user)
    date_approved = fields.Datetime(default=fields.Datetime.now)

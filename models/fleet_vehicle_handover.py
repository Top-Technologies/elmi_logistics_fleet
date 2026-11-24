from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FleetVehicleHandover(models.Model):
    _name = 'fleet.vehicle.handover'
    _description = 'Vehicle and Machinery Handover / Return Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'handover_date desc, id desc'

    name = fields.Char(
        string='Handover Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    mdo_id = fields.Many2one(
        'top.machinery.deployment.order',
        string='Deployment Order (MDO)',
        ondelete='cascade',
        index=True,
    )
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle / Asset',
        required=True,
        tracking=True,
    )
    holder_id = fields.Many2one(
        'hr.employee',
        string='Custodian / Assigned Person',
        required=True,
        tracking=True,
    )
    handover_type = fields.Selection([
        ('issue', 'Handover to Custodian / Site'),
        ('return', 'Return from Custodian / Site'),
    ], string='Handover Type', default='issue', required=True, tracking=True)

    handover_date = fields.Datetime(
        string='Handover Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    meter_reading = fields.Float(
        string='Odometer / Hour Meter Reading',
        required=True,
        tracking=True,
    )
    fuel_level = fields.Selection([
        ('empty', 'Empty (Reserve)'),
        ('quarter', '1/4 Tank'),
        ('half', '1/2 Tank'),
        ('three_quarter', '3/4 Tank'),
        ('full', 'Full Tank'),
    ], string='Fuel Tank Level', default='half', required=True)

    condition_notes = fields.Text(string='Body and Mechanical Condition Notes')
    
    # Checklist of Accessories
    has_spare_tire = fields.Boolean(string='Spare Tire Present', default=True)
    has_jack_tool = fields.Boolean(string='Jack and Wheel Spanner', default=True)
    has_first_aid_kit = fields.Boolean(string='First Aid Kit', default=True)
    has_fire_extinguisher = fields.Boolean(string='Fire Extinguisher', default=True)
    has_warning_triangle = fields.Boolean(string='Warning Triangle', default=True)
    has_vehicle_documents = fields.Boolean(string='Original Libro / Registration Documents', default=True)
    additional_accessories = fields.Char(string='Other Included Accessories / Radios')

    officer_id = fields.Many2one(
        'res.users',
        string='Fleet Dispatcher / Officer',
        default=lambda self: self.env.user,
        tracking=True,
    )
    signature_custodian = fields.Binary(string='Custodian Signature')
    signature_officer = fields.Binary(string='Fleet Officer Signature')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed and Signed'),
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('fleet.vehicle.handover') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            rec.state = 'confirmed'
            # Also log to fleet.meter.reading
            meter_type = 'hours' if rec.vehicle_id.fleet_type == 'heavy' else 'km'
            self.env['fleet.meter.reading'].create({
                ('vehicle_id'): rec.vehicle_id.id,
                ('meter_type'): meter_type,
                ('value'): rec.meter_reading,
                ('reading_date'): rec.handover_date,
                ('source'): 'dispatch',
                ('task_description'): f"Digital Handover ({rec.get_handover_type_display()} - {rec.name})",
                ('operator_id'): rec.holder_id.id,
            })

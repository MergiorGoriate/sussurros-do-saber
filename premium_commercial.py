"""Approved product identities and price calculations in minor currency units."""
from decimal import Decimal, ROUND_HALF_UP
from flask import abort
from models import db
from premium_models import PremiumPlan

TIERS = {'legacy': 'Plano anterior', 'pro': 'Pró', 'max': 'Max'}


def annual_price(monthly_minor):
    return int((Decimal(monthly_minor) * 12 * Decimal('0.80')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def monthly_for(plan):
    if plan.tier not in {'pro', 'max'}: return None
    return PremiumPlan.query.filter_by(tier=plan.tier, interval='monthly', currency=plan.currency).first()


def annual_saving(plan):
    monthly = monthly_for(plan) if plan.interval == 'annual' else None
    if monthly and monthly.price_minor > 0 and plan.price_minor == annual_price(monthly.price_minor):
        return monthly.price_minor * 12 - plan.price_minor
    return None


def validate_price(plan):
    """Protect checkout even when configuration was changed outside the editor."""
    if plan.tier in {'pro','max'} and plan.interval == 'annual':
        monthly = monthly_for(plan)
        if not monthly or monthly.price_minor <= 0 or plan.price_minor != annual_price(monthly.price_minor):
            abort(409, description='O preço anual aguarda confirmação administrativa.')


def apply_price(values, record=None):
    tier = values['tier']
    if tier not in TIERS: raise ValueError('Escolha um nível de plano válido.')
    if record and record.tier in {'pro','max'} and (record.tier,record.interval,record.currency)!=(tier,values['interval'],values['currency']):
        raise ValueError('A identidade de um produto Pró ou Max não pode ser alterada. Crie outro produto para outra moeda.')
    if tier == 'legacy': return
    duplicate = PremiumPlan.query.filter_by(tier=tier, interval=values['interval'], currency=values['currency'])
    if record: duplicate = duplicate.filter(PremiumPlan.id != record.id)
    if duplicate.first(): raise ValueError('Já existe este produto nesta moeda. Edite o plano existente.')
    if record and (record.tier,record.interval,record.currency) != (tier,values['interval'],values['currency']):
        from premium_models import PremiumSubscription, PremiumResource
        from billing_models import BillingOrder
        if (PremiumSubscription.query.filter_by(plan_id=record.id).first() or BillingOrder.query.filter_by(plan_id=record.id).first()
            or any(record.id in row.plan_ids for row in PremiumResource.query.all())):
            raise ValueError('Um plano com contratos ou permissões conserva a sua identidade comercial.')
    if values['interval'] == 'annual':
        monthly = PremiumPlan.query.filter_by(tier=tier,interval='monthly',currency=values['currency']).first()
        if not monthly or monthly.price_minor <= 0:
            if values['active']: raise ValueError('Defina primeiro o preço mensal para calcular o anual.')
            values['price_minor'] = 0
        else:
            values['price_minor'] = annual_price(monthly.price_minor)
            if values['price_minor']>1000000000:raise ValueError('O preço anual excede o limite permitido por período.')


def update_annual(monthly):
    """Never publish a new annual price without administrative confirmation."""
    if monthly.tier not in {'pro','max'} or monthly.interval != 'monthly': return
    annual = PremiumPlan.query.filter_by(tier=monthly.tier,interval='annual',currency=monthly.currency).first()
    if annual and annual.price_minor != annual_price(monthly.price_minor):
        if annual_price(monthly.price_minor)>1000000000:raise ValueError('O preço mensal produz um total anual acima do limite permitido.')
        from premium import audit
        before = annual.price_minor
        annual.price_minor = annual_price(monthly.price_minor)
        annual.active = False
        audit('plan.annual.recalculate',annual,{'before':before,'after':annual.price_minor,'publication_required':True})

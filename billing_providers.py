"""Documented, fixed-host adapters. Responses never become trusted client assertions."""
import os
import re
from decimal import Decimal
from urllib.parse import quote, urlsplit
import requests


class ProviderError(Exception):
    pass


class UnmanagedPayment(ProviderError):
    pass


def enabled(name):
    return os.getenv(name, '').lower() == 'true'


def live_mode():
    return os.getenv('PREMIUM_PAYMENTS_MODE', 'test') == 'live'


def stripe_api(method, path, data=None, key=None):
    if not re.fullmatch(r'/[a-z_]+(?:/[A-Za-z0-9_]+)*(?:/expire)?', path):
        raise ProviderError('Invalid provider path')
    secret = os.getenv('STRIPE_SECRET_KEY','')
    expected = 'sk_live_' if live_mode() else 'sk_test_'
    if not secret.startswith(expected):
        raise ProviderError('Stripe mode or credentials unavailable')
    headers={'Authorization':'Bearer '+secret, 'Stripe-Version':'2025-06-30.basil'}
    if key: headers['Idempotency-Key']=key
    return provider_request(method, 'https://api.stripe.com/v1'+path, headers=headers,
                            **({'params':data} if method=='GET' else {'data':data}))


def provider_request(method, url, **kwargs):
    try:
        response=requests.request(method,url,timeout=(5,25),allow_redirects=False,**kwargs)
        if not 200 <= response.status_code < 300:
            # Never expose raw errors, credentials, phone numbers or full provider bodies.
            raise ProviderError('Provider response requires reconciliation')
        result=response.json()
        if not isinstance(result,dict): raise ValueError()
        return result
    except (requests.RequestException,ValueError) as exc:
        raise ProviderError('Provider unavailable; do not repeat this charge') from None


def available_methods(currency=None, *, configured=True):
    if not enabled('PREMIUM_PAYMENTS_ENABLED'):
        return {}
    if os.getenv('PREMIUM_PAYMENTS_MODE','test') not in {'test','live'}:
        return {}
    if live_mode() and not enabled('PREMIUM_LIVE_APPROVED'):
        return {}
    methods={}
    if os.getenv('CLICPAY_TOKEN') and (currency is None or currency=='MZN'):
        for method,label in [('mpesa','M-Pesa'),('emola','e-Mola'),('netshop','Cartão · ClicPay/NetShop')]:
            if method=='netshop' and not os.getenv('CLICPAY_CHECKOUT_HOSTS'):continue
            if re.fullmatch(r'\d{1,12}',os.getenv('CLICPAY_'+method.upper()+'_WALLET','')):
                methods[method]=label+' · renovação manual'
    secret=os.getenv('STRIPE_SECRET_KEY','')
    if (secret.startswith('sk_live_' if live_mode() else 'sk_test_') and os.getenv('STRIPE_WEBHOOK_SECRET')
            and enabled('STRIPE_MERCHANT_APPROVED') and os.getenv('STRIPE_PORTAL_CONFIGURATION','').startswith('bpc_') and currency in {None,'MZN','USD','EUR','ZAR'}):
        methods['stripe']='Cartão · Stripe · renovação automática'
    if configured:
        from premium_settings import filter_methods
        return filter_methods(methods,currency)
    return methods


def create_clicpay(order, phone, origin=None):
    phone=re.sub(r'[ +()-]','',phone)
    if phone.startswith('258'): phone=phone[3:]
    if order.method!='netshop' and not re.fullmatch(r'8[2-7]\d{7}',phone):
        raise ValueError('Introduza um número moçambicano válido.')
    if order.currency!='MZN' or not 100 <= order.amount_minor <= 15000000:
        raise ValueError('A carteira móvel aceita entre 1 e 150 000 MZN.')
    wallet=os.getenv('CLICPAY_'+order.method.upper()+'_WALLET','')
    if not re.fullmatch(r'\d{1,12}',wallet): raise ProviderError('Wallet unavailable')
    details=provider_request('GET',f'https://clicpay.co.mz/api/v2/wallets/{wallet}',
        headers={'Authorization':'Bearer '+os.getenv('CLICPAY_TOKEN',''),'Accept':'application/json'})
    details=details.get('data') or {}
    expected_environment='production' if order.live else 'sandbox'
    if (str(details.get('id'))!=wallet or details.get('environment')!=expected_environment
        or details.get('is_active') is not True or details.get('allow_c2b') is not True
        or details.get('currency')!='MZN' or (details.get('payment_method') or {}).get('slug')!=order.method):
        raise ProviderError('Wallet environment, currency or permissions mismatch')
    payload={'amount':format(Decimal(order.amount_minor)/100,'.2f'),'reference_description':'Sussurros Premium'}
    endpoint='card-payment' if order.method=='netshop' else 'c2b/'+order.method
    if order.method=='netshop':
        if not origin:raise ProviderError('Public origin required')
        payload.update(callback_url=origin+'/premium/pagamentos/'+order.id,from_app='Sussurros do Saber')
    else:payload.update(msisdn=phone,internal_notes=order.id)
    return provider_request('POST',f'https://clicpay.co.mz/api/v2/wallets/{wallet}/{endpoint}',
        headers={'Authorization':'Bearer '+os.getenv('CLICPAY_TOKEN',''),'Idempotency-Key':order.id,'Accept':'application/json'},json=payload)


def netshop_checkout_url(value):
    allowed={h.strip().lower() for h in os.getenv('CLICPAY_CHECKOUT_HOSTS','').split(',') if h.strip()}
    try:
        parsed=urlsplit(value)
        valid=parsed.scheme=='https' and parsed.netloc.lower() in allowed and not parsed.username and not parsed.password and not parsed.port
    except ValueError:
        valid=False
    if not valid:raise ProviderError('Unapproved NetShop checkout host')
    return value



def clicpay_status(reference):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', reference): raise ProviderError('Invalid reference')
    return provider_request('GET','https://clicpay.co.mz/api/v2/transactions/'+quote(reference,safe='')+'/status',
        headers={'Authorization':'Bearer '+os.getenv('CLICPAY_TOKEN',''),'Accept':'application/json'})


def create_stripe(order, origin):
    data={'mode':'subscription','payment_method_types[0]':'card','client_reference_id':order.id,
          'success_url':origin+'/premium/pagamentos/'+order.id,'cancel_url':origin+'/premium/pagamentos/'+order.id,
          'metadata[billing_order]':order.id,'subscription_data[metadata][billing_order]':order.id,
          'line_items[0][quantity]':'1','line_items[0][price_data][currency]':order.currency.lower(),
          'line_items[0][price_data][unit_amount]':str(order.amount_minor),
          'line_items[0][price_data][product_data][name]':order.snapshot['name'],
          'line_items[0][price_data][recurring][interval]':'month' if order.snapshot['interval']=='monthly' else 'year'}
    result=stripe_api('POST','/checkout/sessions',data,key=order.id)
    if result.get('livemode') is not order.live or result.get('client_reference_id')!=order.id:
        raise ProviderError('Checkout identity mismatch')
    url=result.get('url','')
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.netloc!='checkout.stripe.com' or parsed.username:
        raise ProviderError('Invalid checkout destination')
    if not re.fullmatch(r'cs_[A-Za-z0-9_]+',result.get('id','')):
        raise ProviderError('Invalid session')
    return result


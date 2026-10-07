"""Pinned HTTP destinations and explicitly allowlisted credential references."""
import os,re,socket,ssl,http.client,ipaddress,json,hmac
from urllib.parse import urlsplit
from app.core.config import settings
from app.services.core_hr.common import InvalidOperation


def endpoint(value,resolve=False):
    try:
        p=urlsplit(value)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.fragment or p.query or any(c.isspace() or ord(c)<32 for c in value):raise ValueError()
        port=p.port or (443 if p.scheme=='https' else 80)
        host=p.hostname.encode('idna').decode('ascii')
        if len(host)>253 or '%' in host:raise ValueError()
    except (ValueError,UnicodeError):raise InvalidOperation('Use an http/https endpoint without credentials, query parameters or fragments.') from None
    try:literal=ipaddress.ip_address(host)
    except ValueError:literal=None
    if not settings.allow_private_integration_targets:
        if host.lower()=='localhost' or host.lower().endswith(('.localhost','.local')) or (literal and not literal.is_global):raise InvalidOperation('Private integration destinations are disabled.')
    if not resolve:return p,host,port,None
    try:
        addresses=sorted({item[4][0] for item in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)})
        if not addresses or (not settings.allow_private_integration_targets and any(not ipaddress.ip_address(a).is_global for a in addresses)):raise ValueError()
    except (OSError,ValueError):raise InvalidOperation('Destination resolution failed or resolved to a prohibited network.') from None
    return p,host,port,addresses[0]


def credential(key):
    if not key or not re.fullmatch(r'INTEGRATION_TOKEN_[A-Z0-9_]{1,64}',key) or key not in settings.integration_credential_env_keys:
        raise InvalidOperation('Credential reference is not enabled in local application settings.')
    value=os.environ.get(key)
    if not value or len(value)>4096 or any(ord(c)<33 or ord(c)>126 for c in value):raise InvalidOperation('Integration credential is unavailable.')
    return value


def authorized(key,provided):
    try:expected=credential(key)
    except InvalidOperation:return False
    return bool(provided) and hmac.compare_digest(expected.encode(),provided.encode())


def deliver(definition,payload,delivery_key):
    p,host,port,address=endpoint(definition.endpoint_url,resolve=True)
    token=credential(definition.configuration.credential_env_key) if definition.configuration.auth_type=='BEARER_ENV' else None
    timeout=settings.integration_http_timeout_seconds
    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            self.sock=socket.create_connection((address,port),timeout)
            self.sock=self._context.wrap_socket(self.sock,server_hostname=host)
    connection=PinnedHTTPS(host,port,timeout=timeout,context=ssl.create_default_context()) if p.scheme=='https' else http.client.HTTPConnection(address,port,timeout=timeout)
    headers={'Content-Type':'application/json','Host':p.netloc,'Idempotency-Key':delivery_key}
    if token:headers['Authorization']='Bearer '+token
    try:
        connection.request('POST',p.path or '/',body=json.dumps(payload,ensure_ascii=True).encode(),headers=headers)
        response=connection.getresponse()
        return response.status  # Never follow redirects or retain/log response bodies.
    finally:connection.close()

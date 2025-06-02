import network
import socket
import time
import ure
import ujson
from machine import ADC, Pin
import gc
import usocket
import ssl
import urequests
# ===== Configuración del sensor MQ2 =====
mq2 = ADC(Pin(32))
mq2.atten(ADC.ATTN_11DB)

# ===== Configuración del AP =====
AP_SSID = 'ESP32-AP'
AP_PASS = '12345678'
AP_AUTH = network.AUTH_WPA_WPA2_PSK
ap = None  # Será inicializado en setup_ap()

# ===== Calibración =====
CAL_FILE = 'calibration.json'
# ===== Archivo y variables para límites =====
LIMITS_FILE = 'limits.json'
gasLimit = 0
smokeLimit = 0

# ===== Credenciales para Telegram Bot =====n# Reemplaza con el token de tu bot y el chat ID o user ID destino
define_telegram_credentials = True
TELEGRAM_TOKEN = '8030119069:AAFSY7FVQZ6qApd4C4OH3V5Frr0k7EajGsU'
URL = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN
#https://api.telegram.org/bot7511726909:AAE7Fcxxk-_pLcyTXBqHIWBtwfIgK_F-uwQ/getUpdates
# ===== Preparar interfaz STA (Para luego conectar a una red Wi-Fi) =====
wifi_connected = False
sta_if = None
# ===== Funciones de AP =====
def setup_ap():
    global ap
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASS, authmode=AP_AUTH)
    while not ap.active():
        time.sleep(1)
    print('Access Point activo con IP:', ap.ifconfig()[0])
    return ap

# ===== Gestión de clientes conectados =====
known_clients = set()
def check_new_clients(ap_inst):
    global known_clients
    try:
        # Solo comprobar si el AP está activo
        if not ap_inst.active():
            return
        stations = ap_inst.status('stations') or []
        current = set()
        for s in stations:
            if isinstance(s, (bytes, bytearray)):
                mac = s
            elif isinstance(s, tuple) and len(s) >= 1:
                mac = s[0]
            else:
                continue
            current.add(bytes(mac))
        for mac in current - known_clients:
            mac_str = ':'.join('{:02x}'.format(b) for b in mac)
            print('Nuevo cliente conectado:', mac_str)
        known_clients = current
    except Exception as e:
        # Suprimir errores de modo inválido
        if 'Invalid mode' not in str(e):
            print('Error al verificar clientes:', e)

def load_calibration():
    try:
        with open(CAL_FILE) as f:
            return ujson.load(f).get('gasZeroValue', 0)
    except:
        return 0

def save_calibration(zero_val):
    try:
        data = {'gasZeroValue': zero_val, 'timestamp': time.time()}
        with open(CAL_FILE, 'w') as f:
            ujson.dump(data, f)
    except Exception as e:
        print('Error guardando calibración:', e)

# ===== Funciones para cargar/guardar límites =====
def load_limits():
    global gasLimit, smokeLimit
    try:
        data = ujson.load(open(LIMITS_FILE))
        gasLimit = data.get('gasLimit', 0)
        smokeLimit = data.get('smokeLimit', 0)
    except:
        gasLimit = 0
        smokeLimit = 0

def save_limits():
    try:
        data = {'gasLimit': gasLimit, 'smokeLimit': smokeLimit}
        with open(LIMITS_FILE, 'w') as f:
            ujson.dump(data, f)
    except Exception as e:
        print('Error guardando límites:', e)

# ===== Lectura de gas =====
def gas_porcentaje(sensor_val, tara=0, ref=500):
    pct = ((sensor_val - tara) / ref) * 100
    return max(0, min(100, round(pct, 2)))

# ===== Carga de HTML =====
"""
try:
    with open('index.html') as f:
        HTML_PAGE = f.read()
except:
    HTML_PAGE = '<html><body><h1>Archivo no encontrado</h1></body></html>'
"""

# ===== Envío HTTP =====
def send_header(cl, status_code=200, content_type='text/plain'):
    cl.send(f'HTTP/1.0 {status_code} OK\r\nContent-Type: {content_type}\r\n\r\n')

# ===== Funciones para Telegram =====
def obtenerChatID():
    global TELEGRAM_TOKEN, URL
    try:
        print("TELEGRAM_1",URL)
        res = urequests.get(URL+'/getUpdates')
        print("TELEGRAM_2 VALE = ",res)
        raw = res.text  # no uses .json() directamente
        print("TELEGRAM_2 VALE = ",raw)
        res.close()

        data = ujson.loads(raw)  # usa ujson que es más ligero
        print("TELEGRAM_2 VALE = ",data)
        chat_id = data['result'][0]['message']['chat']['id']
        print("TELEGRAM_2 VALE = ",chat_id)
        print("Tu chat_id es:", chat_id)
        return chat_id
    except Exception as e:
        print("Error al obtener chat_id:", e)
        return None


def telegram_send_minimal(chat_id, text):
    global TELEGRAM_TOKEN
    try:
        gc.collect()
        host = "api.telegram.org"
        text = text.replace(" ", "%20")  # Codifica el mensaje
        path = "/bot{}/sendMessage?chat_id={}&text={}".format(TELEGRAM_TOKEN, chat_id, text)

        addr = socket.getaddrinfo(host, 443)[0][-1]
        s = socket.socket()
        gc.collect()
        s.connect(addr)

        gc.collect()
        s = ssl.wrap_socket(s)

        request = (
            "GET {} HTTP/1.1\r\n"
            "Host: {}\r\n"
            "Connection: close\r\n\r\n"
        ).format(path, host)

        s.write(request.encode())

        # s.read() eliminado para ahorrar RAM
        s.close()
        return True

    except Exception as e:
        print("Error al enviar mensaje:", e)
        return False

# ===== CONECTARME A INTERNET
def do_connect(SSID, PASSWORD):
    global wifi_connected, TELEGRAM_TOKEN
    global sta_if
    sta_if = network.WLAN(network.STA_IF)     # instancia el objeto -sta_if- para controlar la interfaz STA
    if not sta_if.isconnected():              # si no existe conexión...
        sta_if.active(True)                       # activa el interfaz STA del ESP32
        sta_if.connect(SSID, PASSWORD)            # inicia la conexión con el AP
        print('Conectando a la red', SSID +"...")
        while not sta_if.isconnected():           # ...si no se ha establecido la conexión...
            pass                                  # ...repite el bucle...
    print('Configuración de red (IP/netmask/gw/DNS):', sta_if.ifconfig())
    wifi_connected = sta_if.isconnected()


# Para payload grandes, enviamos en bloques
BLOCK_SIZE = 512

def send_payload(cl, payload):
    for i in range(0, len(payload), BLOCK_SIZE):
        cl.send(payload[i:i+BLOCK_SIZE])

# ===== Handlers =====
def handle_get(path, cl, tara):
    if path == '/status':
        send_header(cl)
        cl.send('OK')
    elif path in ['/', '/index.html']:
        send_header(cl, content_type='text/html')
        try:
            with open('index.html') as f:
                for line in f:
                    cl.send(line)
        except:
            cl.send('<html><body><h1>Error cargando index.html</h1></body></html>')
    elif path == '/api/sensor-data':
        try:
            wifi_connected = sta.isconnected()
        except NameError:
            # Si `sta` no está definida, asumimos que no hay conexión Wi-Fi
            wifi_connected = False
        val = mq2.read()
        pct = gas_porcentaje(val, tara)
        data = ujson.dumps({'gasLevel': pct, 'smokeLevel': pct})

        send_header(cl, content_type='application/json')
        cl.send(data)
    elif path == '/api/wifi/scan':
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        nets = sta.scan()  # [(ssid, bssid, channel, RSSI, authmode, hidden), ...]
        results = []
        for ssid_b, bssid, ch, rssi, auth, hidden in nets:
            ssid = ssid_b.decode('utf-8')
            if not ssid or hidden:
                continue
            # map authmode a string
            sec = 'OPEN'
            if auth == 1:
                sec = 'WEP'
            elif auth in (2, 3):
                sec = 'WPA'
            elif auth == 4:
                sec = 'WPA2'
            results.append({
                'ssid': ssid,
                'signal': rssi,
                'security': sec
            })
        data = ujson.dumps(results)
        send_header(cl, content_type='application/json')
        cl.send(data)
    else:
        send_header(cl, status_code=404)
        cl.send('404')


def handle_post(path, req, cl, tara):
    global gasLimit, smokeLimit, AP_SSID, AP_PASS, ap, sta_if
    # extraemos body del req ya leído
    try:
        body = req.split(b'\r\n\r\n', 1)[1]
    except:
        body = b''

    if path in ['/api/sensors/calibrate-zero', '/api/tara']:
        start = time.ticks_ms()
        # calibración no necesita el body parsed
        readings = [mq2.read() for _ in range(20)]
        zero_val = sum(readings) / len(readings)
        tara = zero_val
        resp = ujson.dumps({'success': True, 'gasZeroValue': zero_val})
        send_header(cl, content_type='application/json')
        cl.send(resp)
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        print('Tiempo POST /api/tara:', elapsed, 'ms')
        return tara
    elif path == '/api/limits/update':
        start = time.ticks_ms()
        try:
            params = ujson.loads(body.decode())
            gasLimit = params.get('gasLimit', gasLimit)
            smokeLimit = params.get('smokeLimit', smokeLimit)
            resp = ujson.dumps({'success': True, 'gasLimit': gasLimit, 'smokeLimit': smokeLimit})
        except Exception as e:
            resp = ujson.dumps({'success': False, 'error': str(e)})
        send_header(cl, content_type='application/json')
        cl.send(resp)
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        print('Tiempo POST /api/limits/update:', elapsed, 'ms')
        return tara
    elif path == '/api/wifi/connect':
        try:
            params = ujson.loads(body.decode())
            ssid = params.get('ssid')
            password = params.get('password', '')
            if not ssid:
                raise ValueError('SSID vacío')
            print(f"EL SSID es: {ssid} con psswrd: {password}")
            do_connect(ssid,password)
            if sta_if.isconnected():
                resp = ujson.dumps({'success': True, 'ip': sta_if.ifconfig()[0]})
            else:
                resp = ujson.dumps({'success': False, 'message': 'Timeout al conectar'})
        except Exception as e:
            resp = ujson.dumps({'success': False, 'message': str(e)})
        send_header(cl, content_type='application/json')
        cl.send(resp)
        print("Se envió")
        return tara
    elif path == '/api/access-point/update':
        old_ap_pass = AP_PASS
        old_ap_ssid = AP_SSID
        try:
            params = ujson.loads(body.decode())
            current_pwd = params.get('currentPassword', '')
            new_ssid = params.get('newSSID')
            new_pwd = params.get('newPassword')
            if current_pwd != old_ap_pass:
                raise ValueError('Contraseña actual incorrecta')
            if not new_ssid or not new_pwd:
                raise ValueError('SSID o contraseña nueva vacíos')
            AP_SSID = new_ssid
            AP_PASS = new_pwd
            ap.active(False)
            time.sleep(1)
            ap.config(essid=AP_SSID, password=AP_PASS, authmode=AP_AUTH)
            ap.active(True)
            resp = ujson.dumps({'success': True, 'newSSID': AP_SSID})
            try:
                send_header(cl, content_type='application/json')
                cl.send(resp)
            except OSError:
                pass
            time.sleep(0.5)
            reset()
        except Exception as e:
            resp = ujson.dumps({'success': False, 'message': str(e)})
            try:
                send_header(cl, content_type='application/json')
                cl.send(resp)
            except OSError:
                print("Hubo un error?")
                pass
        return tara
    else:
        send_header(cl, status_code=404)
        cl.send('404')
    return tara
"""
def get_message(message):
    bot.send(message['message']['chat']['id'], message['message']['text'].upper())

def reply_ping(message):
    print(message)
    bot.send(message['message']['chat']['id'], 'pong')
"""
# ===== Bucle principal =====
def main():
    global ap, wifi_connected, TELEGRAM_TOKEN
    gc.collect()
    ap = setup_ap()
    tara = load_calibration()
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    sock = socket.socket()

    try:
        sock.bind(addr)
        sock.listen(1)
        print('Servidor HTTP escuchando en', addr)
        inicializarTelegram = True

        while True:
            gc.collect()
            check_new_clients(ap)
            cl, addr = sock.accept()
            req = cl.recv(2048)
            try:
                req_str = req.decode()
            except:
                cl.close()
                continue

            m = ure.search(r"(GET|POST)\s+(/[^\s]*)", req_str)
            method, path = (m.group(1), m.group(2)) if m else ('GET', '/')
            print('Petición', method, path, 'de', addr, "-- Internet = ", wifi_connected)

            if method == 'GET':
                handle_get(path, cl, tara)
            else:
                tara = handle_post(path, req, cl, tara)

            if wifi_connected and inicializarTelegram:
                try:
                    telegram_send_minimal(8092336325,'ESTO ES UNA PRUEBA DE CONSOLA')
                    inicializarTelegram = False
                except Exception as e:
                    print("Error actualizando Telegram:", e)

            cl.close()

    except KeyboardInterrupt:
        print("\nInterrupción con Ctrl+C detectada. Cerrando socket...")

    except OSError as e:
        print("Error del socket:", e)

    finally:
        sock.close()
        print("Socket cerrado correctamente.")


if __name__ == '__main__':
    main()

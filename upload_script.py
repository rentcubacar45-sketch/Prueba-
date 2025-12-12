import requests
import os
import re
import json
import urllib
from bs4 import BeautifulSoup
import requests_toolbelt as rt
from requests_toolbelt import MultipartEncoderMonitor
from requests_toolbelt import MultipartEncoder
from functools import partial
import uuid
import time
import random
import validators
import mimetypes
import hashlib
import sys
from requests.exceptions import RequestException
from urllib.parse import quote, quote_plus
from random import randint
import mimetypes
from requests.packages.urllib3.exceptions import InsecureRequestWarning
# Disable warnings for unverified HTTPS requests
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Define the SOCKS5 proxy
PROXY = {
    'http': 'socks5h://carlos:659874@152.206.139.83:6046',
    'https': 'socks5h://carlos:659874@152.206.139.83:6046'
}

class UnifiedUploader:
    """Unified uploader class for Moodle, OJS, and Next platforms."""
    def __init__(self, platform, username, password, host, repo_id, file_path=None, max_file_size_mb=999999):
        """
        Inicializa el uploader unificado para Moodle, OJS o Next.

        :param platform: "Moodle", "OJS" o "Next"
        :param username: Nombre de usuario
        :param password: ContraseÃ±a
        :param host: URL base del sitio (e.g., https://moodle.uclv.edu.cu/, https://evea.uh.cu/ o https://minube.uh.cu/)
        :param repo_id: Para Moodle: ID del repositorio (e.g., 4 para cierto repositorio); Para OJS: submissionId; Para Next: No se usa, pero se acepta para compatibilidad
        :param file_path: Ruta al archivo a subir (opcional en init, requerido en upload)
        :param max_file_size_mb: LÃ­mite mÃ¡ximo de tamaÃ±o de archivo en MB
        """
        if platform not in ["Moodle", "OJS", "Next"]:
            raise ValueError("Plataforma debe ser 'Moodle', 'OJS' o 'Next'")
        
        self.platform = platform
        self.username = username
        self.password = password
        self.host = host.rstrip("/")
        self.repo_id = repo_id  # Se acepta para todas las plataformas, pero se ignora en Next
        self.file_path = file_path
        self.proxy = PROXY  # Use the module-level proxy
        self.max_file_size_mb = max_file_size_mb
        self.session = requests.Session()
        self.session.proxies = self.proxy  # Set proxy for the session
        self.userdata = None
        self.userid = ''
        self.sesskey = ''
        self.token = None  # Token for Moodle webservice
        self.baseheaders = {'User-Agent': self._pick_random_user_agent()}
        self.ojs_version = None  # Solo para OJS
        self.ojs_csrf_token = None  # Para OJS

        self._validate_inputs()
        if file_path:
            self._validate_file()

    def _pick_random_user_agent(self) -> str:
        """Selects a random user agent string for HTTP requests.

        Returns:
            str: Random user agent string.
        """
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        ]
        ua = random.choice(user_agents)
        return ua

    def _validate_inputs(self):
        if not self.username or not self.password:
            raise ValueError("Credenciales incompletas")
        if not validators.url(self.host):
            raise ValueError("Host no vÃ¡lido")

    def _validate_file(self) -> None:
        if not os.path.isfile(self.file_path):
            raise FileNotFoundError("Archivo no encontrado")
        file_size_mb = os.path.getsize(self.file_path) / (1024 * 1024)
        if file_size_mb > self.max_file_size_mb:
            raise ValueError(f"Archivo excede lÃ­mite de {self.max_file_size_mb}MB")
        mime_type, _ = mimetypes.guess_type(self.file_path)
        allowed_types = [
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]
        if mime_type not in allowed_types:
            pass

    def _safe_error_message(self, error: Exception, context: str) -> str:
        error_type = type(error).__name__
        error_messages = {
            "ValueError": "OcurriÃ³ un problema con los datos proporcionados. Por favor, verifica e intenta de nuevo.",
            "FileNotFoundError": "El archivo especificado no se encuentra. AsegÃºrate de que la ruta es correcta.",
            "requests.RequestException": "No se pudo conectar al servidor. Verifica tu conexiÃ³n o intenta mÃ¡s tarde.",
            "json.JSONDecodeError": "Error al procesar la respuesta del servidor. Contacta al administrador si persiste.",
            "RuntimeError": "Error inesperado en el servidor. Por favor, intenta de nuevo o contacta al soporte."
        }
        default_message = "OcurriÃ³ un error inesperado. Por favor, intenta de nuevo o contacta al soporte."
        return error_messages.get(error_type, default_message)

    def get_sesskey_or_csrf(self):
        if self.platform == "Moodle":
            fileurl = self.host + '/my/#'
            resp = self.session.get(fileurl, headers=self.baseheaders)
            soup = BeautifulSoup(resp.text, 'html.parser')
            sesskey_elem = soup.find('input', attrs={'name': 'sesskey'})
            if sesskey_elem:
                sesskey = sesskey_elem['value']
                return sesskey
            else:
                raise Exception("No sesskey found")
        elif self.platform == "OJS":
            url = f"{self.host}/login"
            resp = self.session.get(url, headers=self.baseheaders)
            soup = BeautifulSoup(resp.text, 'html.parser')
            token_input = soup.find("input", {"name": "csrfToken"})
            if not token_input:
                raise ValueError("No se encontrÃ³ el token CSRF")
            csrf = token_input["value"]
            return csrf
        elif self.platform == "Next":
            # No se necesita sesskey o CSRF para Next
            return None

    def get_moodle_token(self):
        """
        Obtiene automÃ¡ticamente el token de Moodle usando las credenciales
        
        Returns:
            str: Token de autenticaciÃ³n
        """
        if self.platform != "Moodle":
            return None
        
        token_url = f"{self.host}/login/token.php"
        
        params = {
            'username': self.username,
            'password': self.password,
            'service': 'moodle_mobile_app'
        }
        
        try:
            resp = self.session.get(token_url, params=params, headers=self.baseheaders, verify=False)
            resp.raise_for_status()
            text = resp.text
            data = json.loads(text)
            
            if 'token' in data:
                self.token = data['token']
                return self.token
            else:
                error_msg = data.get('error', 'Error desconocido al obtener token')
                raise ValueError(f"No se pudo obtener el token: {error_msg}")
                
        except Exception as e:
            self.token = None
            return None

    def login(self):
        """Logs into the specified platform (Moodle, OJS, or Next)."""
        try:
            if self.platform == "Moodle":
                login_url = self.host + '/login/index.php'
                resp = self.session.get(login_url, headers=self.baseheaders)
                soup = BeautifulSoup(resp.text, 'html.parser')
                anchor = ''
                try:
                    anchor_elem = soup.find('input', attrs={'name': 'anchor'})
                    if anchor_elem:
                        anchor = anchor_elem['value']
                except:
                    pass
                logintoken = ''
                try:
                    logintoken_elem = soup.find('input', attrs={'name': 'logintoken'})
                    if logintoken_elem:
                        logintoken = logintoken_elem['value']
                except:
                    pass
                payload = {'anchor': anchor, 'logintoken': logintoken, 'username': self.username, 'password': self.password, 'rememberusername': 1}
                resp2 = self.session.post(login_url, data=payload, headers=self.baseheaders)
                counter = 0
                error_lines = []
                for i in resp2.text.splitlines():
                    if "loginerrors" in i or (0 < counter <= 3):
                        counter += 1
                        error_lines.append(i.strip())
                if counter > 0:
                    err_msg = 'Login failed. Error lines: ' + ' '.join(error_lines)
                    raise ValueError(err_msg)
                soup2 = BeautifulSoup(resp2.text, 'html.parser')
                try:
                    userid_elem = soup2.find('div', {'id': 'nav-notification-popover-container'})
                    if userid_elem:
                        self.userid = userid_elem['data-userid']
                except:
                    try:
                        userid_elem = soup2.find('a', {'title': 'Enviar un mensaje'})
                        if userid_elem:
                            self.userid = userid_elem['data-userid']
                    except:
                        pass
                self.userdata = {'token': None}  # Placeholder
                try:
                    self.sesskey = self.get_sesskey_or_csrf()
                except Exception as e:
                    pass
                
                # Intentar obtener token despuÃ©s del login
                self.get_moodle_token()
                
                return True

            elif self.platform == "OJS":
                self.ojs_csrf_token = self.get_sesskey_or_csrf()
                login_data = {
                    "csrfToken": self.ojs_csrf_token,
                    "username": self.username,
                    "password": self.password,
                    "remember": "1",
                    "source": ""
                }
                login_url = f"{self.host}/login/signIn"
                resp = self.session.post(login_url, data=login_data, headers=self.baseheaders)
                if resp.status_code >= 400 or "Salir" not in resp.text:
                    err_msg = "Error en login para OJS"
                    raise ValueError(err_msg)
                return True

            elif self.platform == "Next":
                self.session.auth = (self.username, self.password)
                return True  # Asumimos Ã©xito; fallarÃ¡ en upload si credenciales incorrectas

        except Exception as e:
            return False

    def detect_ojs_version(self):
        if self.platform != "OJS":
            return
        try:
            url = f"{self.host}/login"
            resp = self.session.get(url, headers=self.baseheaders)
            soup = BeautifulSoup(resp.text, "html.parser")
            meta = soup.find("meta", {"name": "generator"})
            if meta and meta.get("content"):
                self.ojs_version = meta["content"].replace("Open Journal Systems ", "")
            else:
                self.ojs_version = "3.3.0"
        except Exception as e:
            raise RuntimeError(self._safe_error_message(e, "detect_ojs_version")) from e

    def is_ojs_3_4_plus(self) -> bool:
        if not self.ojs_version:
            return False
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", self.ojs_version)
        if not match:
            return False
        major, minor, _ = map(int, match.groups())
        is_plus = major > 3 or (major == 3 and minor >= 4)
        return is_plus

    def _upload_with_token(self, progressfunc=None, args=(), tokenize=False):
        """
        Sube un archivo a Moodle usando el mÃ©todo de token y genera una URL pÃºblica
        Adaptado a sÃ­ncrono desde el cliente async proporcionado.
        
        Args:
            progressfunc: Callback para progreso (adaptado para multipart si es posible)
            args: Argumentos para el callback
            tokenize: Si usar token en la URL (por compatibilidad)
            
        Returns:
            tuple: (error_msg or None, data dict with 'url')
        """
        try:
            if not self.token:
                raise ValueError("No token available for upload")

            url = self.host + "/webservice/upload.php"
            filename = os.path.basename(self.file_path)
            mime_type, _ = mimetypes.guess_type(self.file_path)
            file_mime = mime_type or 'application/octet-stream'

            # Preparar FormData para subida
            files = {
                'token': (None, self.token),
                'file': (filename, open(self.file_path, 'rb'), file_mime)
            }
            
            # Para progreso, usar MultipartEncoderMonitor si progressfunc estÃ¡ presente
            if progressfunc:
                b = uuid.uuid4().hex
                encoder = MultipartEncoder(files, boundary=b)
                progrescall = CallingUpload(progressfunc, filename, args)
                callback = partial(progrescall)
                monitor = MultipartEncoderMonitor(encoder, callback=callback)
                upload_headers = {"Content-Type": monitor.content_type, **self.baseheaders}
                resp = self.session.post(url, data=monitor, headers=upload_headers, verify=False)
            else:
                resp = self.session.post(url, files=files, headers=self.baseheaders, verify=False)

            resp.raise_for_status()
            text = resp.text
            dat = json.loads(text)[0]

            # Construir URL base del draft
            url_base = self.host + "/draftfile.php/" + str(dat["contextid"]) + "/user/draft/" + str(dat["itemid"]) + "/" + str(quote(dat["filename"]))

            # Crear evento para obtener URL pÃºblica (adaptado de async)
            urlw = self.host + "/webservice/rest/server.php?moodlewsrestformat=json"
            
            query = {
                "formdata": f"name=Event&eventtype=user&timestart[day]=31&timestart[month]=9&timestart[year]=3786&timestart[hour]=00&timestart[minute]=00&description[text]={quote_plus(url_base)}&description[format]=1&description[itemid]={randint(100000000, 999999999)}&location=&duration=0&repeat=0&id=0&userid={dat['userid']}&visible=1&instance=1&_qf__core_calendar_local_event_forms_create=1",
                "moodlewssettingfilter": "true",
                "moodlewssettingfileurl": "true",
                "wsfunction": "core_calendar_submit_create_update_form",
                "wstoken": self.token
            }
            
            resp_event = self.session.post(urlw, data=query, headers=self.baseheaders, verify=False)
            resp_event.raise_for_status()
            text_event = resp_event.text
            
            try:
                response_data = json.loads(text_event)
                if "event" in response_data and "description" in response_data["event"]:
                    urls = re.findall(r"https?://[^\s<>]+[a-zA-Z0-9]", response_data["event"]["description"])
                    if urls:
                        public_url = urls[-1].replace("draftfile.php/", "webservice/draftfile.php/") + "?token=" + self.token
                    else:
                        # Fallback
                        public_url = url_base.replace("draftfile.php/", "webservice/draftfile.php/") + "?token=" + self.token
                else:
                    # Fallback
                    public_url = url_base.replace("draftfile.php/", "webservice/draftfile.php/") + "?token=" + self.token
            except (KeyError, json.JSONDecodeError, IndexError) as e:
                # Fallback seguro
                public_url = url_base.replace("draftfile.php/", "webservice/draftfile.php/") + "?token=" + self.token

            if tokenize and self.userdata and self.userdata.get('token'):
                public_url = public_url.replace('pluginfile.php/', 'webservice/pluginfile.php/') + '?token=' + self.userdata['token']

            data = {'url': public_url, 'normalurl': public_url}
            return None, data

        except Exception as e:
            return str(self._safe_error_message(e, "_upload_with_token")), None

    def upload_file(self, file_path=None, progressfunc=None, args=(), tokenize=False):
        if file_path:
            self.file_path = file_path
        self._validate_file()

        if self.platform == "Moodle":
            # Primero intentar con token si estÃ¡ disponible
            if self.token:
                return self._upload_with_token(progressfunc, args, tokenize)
            else:
                return self._upload_to_moodle(progressfunc, args, tokenize)
        elif self.platform == "OJS":
            self.detect_ojs_version()
            return self._upload_to_ojs()
        elif self.platform == "Next":
            return self._upload_to_next()

    def _upload_to_moodle(self, progressfunc, args, tokenize):
        try:
            file_edit = f'{self.host}/user/files.php'
            resp = self.session.get(file_edit, headers=self.baseheaders)
            if resp.status_code != 200:
                raise Exception(f"Failed to load files.php: status {resp.status_code}")
            soup = BeautifulSoup(resp.text, 'html.parser')
            sesskey_elem = soup.find('input', attrs={'name': 'sesskey'})
            if not sesskey_elem:
                raise Exception("No sesskey input found")
            sesskey = sesskey_elem['value']

            obj_elem = soup.find('object', attrs={'type': 'text/html'})
            if not obj_elem:
                raise Exception("No object embed found for file picker")
            query_url = obj_elem['data']
            query = self.extract_query(query_url)

            filemanager_div = soup.find('div', {'class': 'filemanager'})
            if filemanager_div:
                client_id = str(filemanager_div['id']).replace('filemanager-', '')
            else:
                # Fallback to regex search
                client_id_pattern = r'"client_id":"(\w{13})"'
                match = re.search(client_id_pattern, resp.text)
                if match:
                    client_id = match.group(1)
                else:
                    raise Exception("No client_id found")

            upload_file_url = f'{self.host}/repository/repository_ajax.php?action=upload'
            of = open(self.file_path, 'rb')
            b = uuid.uuid4().hex
            title = os.path.basename(self.file_path)
            mime_type, _ = mimetypes.guess_type(self.file_path)
            file_mime = mime_type or 'application/octet-stream'
            upload_data = {
                'title': (None, title),
                'author': (None, self.username),
                'license': (None, 'allrightsreserved'),
                'itemid': (None, query['itemid']),
                'repo_id': (None, str(self.repo_id)),
                'p': (None, ''),
                'page': (None, ''),
                'env': (None, query['env']),
                'sesskey': (None, sesskey),
                'client_id': (None, client_id),
                'maxbytes': (None, query['maxbytes']),
                'areamaxbytes': (None, str(1024 * 1024 * 1024 * 4)),  # Hack para bypass de lÃ­mite (4GB)
                'ctx_id': (None, query['ctx_id']),
                'savepath': (None, '/')
            }
            upload_file = {
                'repo_upload_file': (title, of, file_mime),
                **upload_data
            }
            encoder = rt.MultipartEncoder(upload_file, boundary=b)
            progrescall = CallingUpload(progressfunc, os.path.basename(self.file_path), args)
            callback = partial(progrescall)
            monitor = MultipartEncoderMonitor(encoder, callback=callback)
            resp2 = self.session.post(upload_file_url, data=monitor,
                                      headers={"Content-Type": monitor.content_type, **self.baseheaders},
                                      allow_redirects=False)
            of.close()

            if resp2.status_code != 200:
                raise Exception(f"Upload failed with status {resp2.status_code}: {resp2.text}")

            data = json.loads(resp2.text)

            if 'error' in data:
                raise Exception(f"Upload error: {data['error']}")

            if 'event' in data and data['event'] == 'fileexists':
                data['url'] = data['existingfile']['url']

            # Save the draft area after upload
            _qf_elem = soup.find('input', {'name': '_qf__core_user_form_private_files'})
            if _qf_elem:
                _qf = _qf_elem['value']
                saveUrl = self.host + '/lib/ajax/service.php?sesskey=' + sesskey + '&info=core_form_dynamic_form'
                savejson = [{"index": 0, "methodname": "core_form_dynamic_form",
                             "args": {"formdata": f"sesskey={sesskey}&_qf__core_user_form_private_files={_qf}&files_filemanager={query['itemid']}",
                                      "form": "core_user\\form\\private_files"}}]
                headers = {'Content-type': 'application/json', 'Accept': 'application/json, text/javascript, */*; q=0.01',
                           **self.baseheaders}
                resp_save = self.session.post(saveUrl, json=savejson, headers=headers)
                if resp_save.status_code != 200:
                    pass
            else:
                pass

            data['url'] = str(data['url']).replace('\\', '')
            data['normalurl'] = data['url']
            if self.userdata and self.userdata.get('token') and not tokenize:
                data['url'] = str(data['url']).replace('pluginfile.php/', 'webservice/pluginfile.php/') + '?token=' + self.userdata['token']
            return None, data
        except Exception as e:
            return str(self._safe_error_message(e, "_upload_to_moodle")), None

    def _upload_to_ojs(self):
        try:
            if not self.ojs_csrf_token:
                self.ojs_csrf_token = self.get_sesskey_or_csrf()

            # Get upload csrf if different
            wizard_url = f"{self.host}/submission/wizard/2?submissionId={self.repo_id}#step-2"
            resp = self.session.get(wizard_url, headers=self.baseheaders)
            csrf_match = re.search(r'"csrfToken":"([^"]+)"', resp.text)
            if csrf_match:
                self.ojs_csrf_token = csrf_match.group(1)

            temp_id = None
            if self.is_ojs_3_4_plus():
                with open(self.file_path, 'rb') as f:
                    form_data = rt.MultipartEncoder({'file': (os.path.basename(self.file_path), f)})
                    temp_url = f"{self.host}/api/v1/temporaryFiles"
                    resp_temp = self.session.post(temp_url, data=form_data,
                                                  headers={"Content-Type": form_data.content_type, "X-Csrf-Token": self.ojs_csrf_token, **self.baseheaders})
                    if resp_temp.status_code != 200:
                        raise Exception(f"Temporary upload failed: {resp_temp.status_code}")
                    json_resp = resp_temp.json()
                    temp_id = json_resp.get('temporaryFileId')
                    if not temp_id:
                        raise ValueError("No temporaryFileId received")

            with open(self.file_path, 'rb') as f:
                form_data = rt.MultipartEncoder({
                    'file': (os.path.basename(self.file_path), f),
                    'fileStage': (None, '2'),
                    'name[es_ES]': (None, os.path.basename(self.file_path)),
                    'temporaryFileId': (None, str(temp_id)) if temp_id else (None, '')
                })
                upload_url = f"{self.host}/api/v1/submissions/{self.repo_id}/files"
                resp_upload = self.session.post(upload_url, data=form_data,
                                                headers={"Content-Type": form_data.content_type, "X-Csrf-Token": self.ojs_csrf_token, **self.baseheaders})
                if resp_upload.status_code != 200:
                    raise Exception(f"Upload failed: {resp_upload.status_code} - {resp_upload.text}")
                json_response = resp_upload.json()
                download_link = json_response.get('url')
                if not download_link:
                    raise ValueError("No url in response")
                return None, {'url': download_link}
        except Exception as e:
            return str(self._safe_error_message(e, "_upload_to_ojs")), None

    def _upload_to_next(self):
        try:
            if not os.path.exists(self.file_path):
                err_msg = f'Archivo no encontrado: {self.file_path}'
                raise FileNotFoundError(err_msg)

            nombre_final = os.path.basename(self.file_path)
            base_uploads = f"{self.host}/remote.php/dav/uploads/{self.username}"
            destino_temporal = f"{self.host}/remote.php/dav/files/{self.username}/{nombre_final}"
            temp_folder = self._generar_nombre_carpeta_temporal()

            temp_dir_url = f"{base_uploads}/{temp_folder}"
            headers = {'Destination': destino_temporal}
            response = self.session.request('MKCOL', temp_dir_url, headers=headers)
            if response.status_code not in [201, 405]:
                err_msg = f"Error al crear carpeta: {response.status_code} - {response.text}"
                raise Exception(err_msg)

            tamaño_archivo = os.path.getsize(self.file_path)
            chunk_url = f"{base_uploads}/{temp_folder}/{nombre_final}"
            headers = {
                'Destination': destino_temporal,
                'Content-Length': str(tamaño_archivo),
                'OC-Total-Length': 'A',  # Bypass de cuota
                'X-Expected-Entity-Length': str(tamaÃ±o_archivo)
            }
            with open(self.file_path, 'rb') as archivo:
                response = self.session.put(chunk_url, headers=headers, data=archivo)
                if response.status_code != 201:
                    err_msg = f'Error en chunk {nombre_final}: {response.status_code} - {response.text}'
                    raise Exception(err_msg)

            # Eliminar archivo en destino temporal si existe
            response = self.session.delete(destino_temporal)
            if response.status_code in [204, 200]:
                pass
            else:
                pass

            enlace_descarga = f"{temp_dir_url}/{nombre_final}"
            return None, {'url': enlace_descarga}
        except Exception as e:
            return str(self._safe_error_message(e, "_upload_to_next")), None

    def _generar_nombre_carpeta_temporal(self):
        timestamp = str(int(time.time() * 1000))
        hash_str = hashlib.md5(os.urandom(16)).hexdigest()[:16]
        return f"web-file-upload-{hash_str}-{timestamp}"

    def extract_query(self, url):
        tokens = str(url).split('?')
        if len(tokens) < 2:
            return {}
        params = tokens[1].split('&')
        retQuery = {}
        for q in params:
            if '=' in q:
                qspl = q.split('=', 1)
                key = qspl[0]
                value = urllib.parse.unquote_plus(qspl[1])
                retQuery[key] = value
            else:
                retQuery[q] = None
        return retQuery

    def logout(self):
        try:
            if self.platform == "Moodle":
                logouturl = self.host + '/login/logout.php?sesskey=' + self.sesskey
                resp = self.session.post(logouturl, headers=self.baseheaders)
            elif self.platform == "OJS":
                logout_url = f"{self.host}/login/signOut"
                resp = self.session.get(logout_url, headers=self.baseheaders)
            elif self.platform == "Next":
                # No logout especÃ­fico para WebDAV/Next, solo cerrar sesiÃ³n
                self.session.close()
        except Exception as e:
            pass

    def delete_temp_folder(self, temp_folder):
        temp_folder = temp_folder.lstrip('/')
        folder_url = f"{self.host}/remote.php/dav/uploads/{self.username}/{temp_folder}"
        resp = self.session.request('DELETE', folder_url)
        return resp.status_code in (204, 200)

class CallingUpload:
    def __init__(self, func, filename, args):
        self.func = func
        self.args = args
        self.filename = filename
        self.time_start = time.time()
        self.time_total = 0
        self.speed = 0
        self.last_read_byte = 0

    def __call__(self, monitor):
        try:
            self.speed += monitor.bytes_read - self.last_read_byte
            self.last_read_byte = monitor.bytes_read
            tcurrent = time.time() - self.time_start
            self.time_total += tcurrent
            self.time_start = time.time()
            if self.time_total >= 1:
                remaining_bytes = monitor.len - monitor.bytes_read
                clock_time = remaining_bytes / self.speed if self.speed > 0 else 0
                if self.func:
                    self.func(self.filename, monitor.bytes_read, monitor.len, self.speed, clock_time, self.args)
                self.time_total = 0
                self.speed = 0
        except Exception as e:
            pass

def progress_callback(filename, bytes_read, total_bytes, speed, estimated_time, args):
    percent = (bytes_read / total_bytes) * 100
    print(f"Subiendo {filename}: {percent:.1f}% ({bytes_read}/{total_bytes} bytes) - Velocidad: {speed} bytes/s - Tiempo estimado: {estimated_time:.1f}s")

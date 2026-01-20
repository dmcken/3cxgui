

# System
import datetime
import logging
import urllib.parse

# External
import fake_useragent
import requests

logger = logging.getLogger(__name__)

class HttpError(RuntimeError):
    pass

class GUIError(RuntimeError):
    pass

class cxgui:
    '''3CX GUI main class'''

    def __init__(self, domain: str, ssl: bool = True):
        """Constructor.

        Args:
            domain (str): Domain name of server.
            ssl (bool, optional): Is the domain SSL enabled. Defaults to True.
        """
        domain = domain.strip()
        if domain[-1] == '/':
            # Strip trailing slash, if present
            domain = domain[:-1]
        self._domain = domain
        self._ssl = ssl

        # General initialization
        ua = fake_useragent.UserAgent()
        self._user_agent = ua.firefox
        self._username = None
        self._password = None
        self._cookie_jar = None
        self._access_token = None
        self._refresh_token = None
        self._auth_token = None
        self._session = requests.Session()

    def _build_url(self, relative_url: str) -> str:
        """Build absolute URL from a relative path.

        Args:
            relative_url (str): Relative URL to build upon.

        Returns:
            str: _description_
        """
        return ("https" if self._ssl else "http") + f"://{self._domain}" +\
            ('' if relative_url[0] == '/' else '/') + relative_url


    def _build_headers(self, include_auth: bool = True) -> dict[str,str]:
        """Build headers for use in requests.

        Returns:
            dict[str,str]: Headers dictionary.
        """
        temp = {
            'Accept': 'application/json',
            'User-Agent': self._user_agent,
        }
        if include_auth is True:
            logger.error(f"Including auth")
            temp['Authorization'] = f"Bearer {self._auth_token}"
        return temp

    def _display_debug(self, response):
        """Display debug data of a response.

        Args:
            response (_type_): _description_
        """
        logger.debug("REQUEST")
        logger.debug(response.request.method, response.request.url)
        logger.debug(response.request.headers)
        logger.debug(response.request.body)

        logger.debug("\nRESPONSE")
        logger.debug(response.status_code)
        logger.debug(response.headers)
        logger.debug(response.text)

        return

    def login(self, username: str, password: str) -> bool:
        """Login to 3CX server.

        Args:
            username (str): Username to login as.
            password (str): Password to login as.

        Raises:
            RuntimeError: _description_
            RuntimeError: _description_
            RuntimeError: _description_

        Returns:
            bool: True if we successfully logged in, False otherwise.
        """
        self._username = username
        self._password = password

        result = self._session.post(
            url=self._build_url('/webclient/api/Login/GetAccessToken'),
            json={
                "ReCaptchaResponse": None,
                "SecurityCode":"",
                "Password":self._password,
                "Username":self._username,
            },
            headers=self._build_headers(False)
        )
        if result.status_code not in [200]:
            raise HttpError(f"Invalid HTTP status when logging in: {result.status_code}")

        result_json = result.json()
        if result_json['Status'] not in ['AuthSuccess']:
            raise GUIError(f"Unknown 3CX status when logging in: {result_json['Status']}")

        if result_json['Token']['token_type'] not in ['Bearer']:
            raise GUIError(f"Unknown token type: {result_json['Token']['token_type']}")

        self._access_token = result_json['Token']['access_token']
        self._refresh_token = result_json['Token']['refresh_token']

        token_result = self._session.post(
            url=self._build_url('/connect/token'),
            data={
                'client_id': 'Webclient',
                'grant_type': 'refresh_token',
            },
            headers=self._build_headers(False)
        )
        result_roken_json = token_result.json()
        self._auth_token = result_roken_json['access_token']

        logger.error(f"Tokens:\n{self._access_token}\n" +\
            f"{self._refresh_token}\n{self._auth_token}")

        return True

    def backup_fetch_list(self, fname_filter: str = None) -> dict:
        """Fetch the backup list.

        Args:
            fname_filter (str, optional): Filter the list by the filename specified. Defaults to None.

        Raises:
            RuntimeError: _description_

        Returns:
            dict: _description_
        """
        logging.getLogger("urllib3").setLevel(logging.DEBUG)

        result = self._session.get(
            url=self._build_url('/xapi/v1/Backups'),
            params={
                '$top': 50,
                "$skip": 0,
                # The space after CreationTime is causing issues (should be
                # encoded as %20 but is coming through as +).
                #"$ordeby": urllib.parse.quote("CreationTime desc", safe=""),
                "$select": "CreationTime,Size,FileName,DownloadLink",
            },
            headers=self._build_headers(),
        )
        self._display_debug(result)

        if result.status_code not in [200]:
            raise HttpError(f"Invalid HTTP status when pulling backup list in: {result.status_code}")

        raw_json = result.json()['value']
        if fname_filter is not None:
            # Only return the entry matching that entry if it exists
            output = list(filter(lambda x: x['FileName'] == fname_filter, raw_json))
            return output
        else:
            return raw_json

    def backup_start(self, out_filename: str = None) -> str:
        """Trigger a new backup.

        Args:
            out_filename (str, optional): The user can specify the desired filename, otherwise one is autogenerated. Defaults to None.

        Raises:
            RuntimeError: Invalid status code.

        Returns:
            str: Filename to set for the backup.
        """
        if out_filename is None:
            today = datetime.date.isoformat(datetime.date.today())
            filename = f"CDRDump-{today}.zip"
        else:
            #  TODO: Add sanity checks.
            filename = out_filename

        result = self._session.post(
            url=self._build_url('/xapi/v1/Backups/Pbx.Backup'),
            json={
                'description': {
                    "Name": filename,
                    "Contents":{
                        "Recordings": False,
                        "EncryptBackup": False,
                        "FQDN": True,
                        "CallHistory": True,
                        "License": True,
                        "PhoneProvisioning": True,
                        "Prompts": True,
                        "VoiceMails": True,
                        "DisableBackupCompression": False,
                    },
                },
            },
            headers=self._build_headers(),
        )

        if result.status_code not in [200,204]:
            if result.status_code in [400]:
                data = result.json()
                if data['error']['details'][0]['message'] == "WARNINGS.XAPI.DUPLICATE":
                    logger.error("Duplicate backup detected")
                    return filename
            raise HttpError(f"Invalid HTTP status when creating backup: {result.status_code} -> {result.text}")

        return filename

    def backup_download(self, download_link: str, output_file: str):
        """Download a backup from the 3CX server.

        Args:
            download_link (str): URL to download from.
            output_file (str): Output file to save download to.
        """

        with requests.get(self._build_url(download_link), stream=True) as r:
            r.raise_for_status()  # fail fast on HTTP errors
            with open(output_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:  # filters out keep-alive chunks
                        f.write(chunk)

        return

    def backup_delete(self, filename: str):
        """Delete a backup.

        Args:
            filename (str): _description_

        https://<domain>/xapi/v1/Backups('CDRDump-2026-01-19.zip')
        """
        result = self._session.delete(
            url=self._build_url(f"/xapi/v1/Backups('{filename}')"),
            headers=self._build_headers(),
        )
        if result.status_code not in [204]:
            raise HttpError(f"Invalid HTTP code '{result.status_code}' deleting backup")

        return


if __name__ == '__main__':
    import dotenv
    import pprint
    import time
    import zipfile

    logging.basicConfig(level=logging.DEBUG)

    config = dotenv.dotenv_values()
    x = cxgui(config['DOMAIN'])
    x.login(config['USERNAME'],config['PASSWORD'])

    output_fname = x.backup_start()
    while (backup_obj := x.backup_fetch_list(output_fname)) == []:
        time.sleep(2)

    x.backup_download(
        backup_obj[0]['DownloadLink'],
        backup_obj[0]['FileName'],
    )

    with zipfile.ZipFile(output_fname) as archive:
        for curr_file in ['cdrbilling','cdroutput']:
            with archive.open(f'DbTables/{curr_file}.csv') as f_in, \
                open(f'{curr_file}.csv', 'w', encoding='utf-8') as f_out:
                f_out.write(f_in.read().decode('utf-8'))

    x.backup_delete(output_fname)

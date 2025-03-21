import os
import mimetypes
import re
import requests
from io import BytesIO

base_url = 'http://telegra.ph'
save_url = 'https://edit.telegra.ph/save'
upload_file_url = 'https://telegra.ph/upload'


class Error(Exception):
    pass


class GetImageRequestError(Error):
    pass


class ImageUploadHTTPError(Error):
    pass


class FileTypeNotSupported(Error):
    pass


def _check_mimetypes(mime_type):
    return mime_type in ('image/jpeg', 'image/png', 'image/gif', 'video/mp4')


def _get_mimetype_from_response_headers(headers):
    types = re.split(r'[;,]', headers.get('Content-Type', ''))
    if types:
        ext = mimetypes.guess_extension(types[0], strict=False)
        if ext:
            return mimetypes.types_map.get(ext, mimetypes.common_types.get(ext, ''))
    return ''


def upload_image(file_name_or_url,
                 user_agent='Python_telegraph_poster/0.1',
                 return_json=False,
                 get_timeout=(10.0, 10.0),
                 upload_timeout=(7.0, 7.0)):
    close_file = False  # Flag to close local file later

    # Determine the source type and set filename, file object, and MIME type.
    if hasattr(file_name_or_url, 'read') and hasattr(file_name_or_url, 'name'):
        # file-like object with a name attribute
        img = file_name_or_url
        filename = os.path.basename(file_name_or_url.name)
        img_content_type = mimetypes.guess_type(file_name_or_url.name)[0]
    elif re.match(r'^https?://', file_name_or_url, flags=re.IGNORECASE):
        # URL case
        try:
            response = requests.get(file_name_or_url, headers={'User-Agent': user_agent}, timeout=get_timeout)
        except Exception as e:
            raise GetImageRequestError('Url request failed: ' + str(e))
        if response.status_code != 200 or 'Content-Type' not in response.headers:
            raise GetImageRequestError('Url request failed with status code: ' + str(response.status_code))
        img_content_type = _get_mimetype_from_response_headers(response.headers)
        img = BytesIO(response.content)
        filename = 'blob'
    else:
        # Local file path: open the file as a file object
        filename = os.path.basename(file_name_or_url)
        img_content_type = mimetypes.guess_type(file_name_or_url)[0]
        try:
            img = open(file_name_or_url, 'rb')
            close_file = True
        except Exception as e:
            raise Exception('Failed to open file: ' + str(e))

    # Check if the file type is supported.
    if not _check_mimetypes(img_content_type):
        if close_file:
            img.close()
        raise FileTypeNotSupported('The "%s" filetype is not supported' % img_content_type)

    headers = {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Referer': base_url + '/',
        'User-Agent': user_agent
    }

    # Use the actual filename instead of a generic 'blob'
    files = {
        'file': (filename, img, img_content_type)
    }
    try:
        json_response = requests.post(upload_file_url, timeout=upload_timeout, files=files, headers=headers)
    except requests.exceptions.ReadTimeout:
        if close_file:
            img.close()
        raise ImageUploadHTTPError('Request timeout')

    if close_file:
        img.close()

    if json_response.status_code == requests.codes.ok and json_response.content:
        try:
            json_data = json_response.json()
        except Exception as e:
            print("JSON decode error:", e)
            print("Response content:", json_response.content)
            raise Exception('Error while uploading the image')
        if return_json:
            return json_data
        elif isinstance(json_data, list) and len(json_data):
            if 'src' in json_data[0]:
                return base_url + json_data[0]['src']
            else:
                print("Unexpected response list format:", json_data)
                raise Exception('Error while uploading the image')
        elif isinstance(json_data, dict):
            if json_data.get('error') == 'File type invalid':
                raise FileTypeNotSupported('This file is unsupported')
            else:
                return str(json_data)
    else:
        # Debug output in case of error.
        print("Upload error: Status", json_response.status_code, "Content:", json_response.content)
        raise Exception('Error while uploading the image')

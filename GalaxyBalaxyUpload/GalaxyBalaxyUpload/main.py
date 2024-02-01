import os
from os.path import basename, splitext
import requests
import re
from mutagen import File
from mutagen.flac import FLAC
from pydub import AudioSegment
import matplotlib.pyplot as plt
import pyperclip
import logging
import numpy as np
from requests.exceptions import RequestException
from GalaxyBalaxyUpload.config import (
    PASTEBIN_API_KEY,
    PASTEBIN_USER_KEY,
    GITHUB_TOKEN,
    IMGUR_CLIENT_ID,
    LOG_FILENAME,
    PASTEBIN_API_URL,
    GITHUB_GISTS_API_URL,
)

from enum import Enum

class EncodingType(Enum):
    LOSSLESS = "Lossless"
    LOSSY = "Lossy"

ARTIST_TRACK_PATTERN = re.compile(r"(\d+)-(\d+) (.+)\.flac")


def get_audio_info(file_path):
    try:
        # Extract disc number, track number, and title using regex
        match = ARTIST_TRACK_PATTERN.match(basename(file_path))
        if match:
            disc_number, track_number, title = match.groups()  # Corrected group extraction
            
            # Extract extension separately
            _, extension = splitext(file_path)
            
            # Use lower() to ensure case-insensitive matching
            extension = extension.lower()

            # Initialize default values
            bitrate_kbps = "N/A"
            sample_rate = "N/A"
            channels = "N/A"
            bit_depth = "N/A"
            codec = extension[1:]  # Correctly remove the dot from the extension
            encoding = EncodingType.LOSSY

            # Process FLAC files
            if codec == "flac":
                audio = FLAC(file_path)
                if audio.info:
                    bitrate_kbps = str(int(audio.info.bitrate / 1000))
                    sample_rate = str(audio.info.sample_rate)
                    channels = str(audio.info.channels)
                    bit_depth = str(audio.info.bits_per_sample)
                    encoding = EncodingType.LOSSLESS

            return bitrate_kbps, sample_rate, channels, bit_depth, codec, encoding
        else:
            logging.warning(f"File '{file_path}' does not match the expected format.")
            return "N/A", "N/A", "N/A", "N/A", "N/A", EncodingType.LOSSY
    except Exception as e:
        logging.error(f"Failed to get audio info for {file_path}: {e}")
        return "N/A", "N/A", "N/A", "N/A", "N/A", EncodingType.LOSSY

def replace_artist_with_track_number(tracks, bitrates):
    reformatted_tracks = []
    for track_number, (track, bitrate) in enumerate(zip(tracks, bitrates), start=1):
        match = ARTIST_TRACK_PATTERN.match(track)
        if match:
            title = match.group(3)  # Use the third group which captures the track title
            formatted_track_number = f"{track_number:02d}"
            new_track = f"{formatted_track_number} - {title} [{bitrate}k]"
            reformatted_tracks.append(new_track)
        else:
            logging.warning(f"Track '{track}' does not match the expected format.")
            reformatted_tracks.append(track)  # Append as is or handle differently
    return reformatted_tracks

def upload_to_pastebin(api_key, user_key, title, text):
    data = {
        'api_dev_key': api_key,
        'api_user_key': user_key,
        'api_option': 'paste',
        'api_paste_code': text,
        'api_paste_private': '1',  # 0=public, 1=unlisted, 2=private
        'api_paste_expire_date': 'N', # Never expires
        'api_paste_name': title,
    }
    try:
        response = requests.post(PASTEBIN_API_URL, data=data)
        if response.status_code == 200:
            logging.info("Pastebin upload successful.")
            return response.text
        else:
            logging.error(f"Pastebin upload failed with status code {response.status_code}. Response: {response.text}")
            return None
    except RequestException as e:
        logging.error(f"Pastebin upload failed with exception: {e}")
        return None


def upload_to_gist(token, title, text):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json',
    }
    data = {
        'description': title,
        'public': False,
        'files': {
            f'{title}.txt': {
                'content': text,
            },
        },
    }
    try:
        response = requests.post(GITHUB_GISTS_API_URL, headers=headers, json=data)
        if response.status_code == 201:
            gist_url = response.json()['html_url']
            logging.info(f"Gist upload successful. URL: {gist_url}")
            return gist_url
        else:
            logging.error(f"Gist upload failed with status code {response.status_code}. Response: {response.json()}")
            return None
    except RequestException as e:
        logging.error(f"Gist upload failed with exception: {e}")
        return None


def upload_to_imgur(image_path, client_id):
    url = "https://api.imgur.com/3/upload"
    headers = {"Authorization": f"Client-ID {client_id}"}

    with open(image_path, 'rb') as f:
        files = {'image': (os.path.basename(image_path), f)}
        response = requests.post(url, headers=headers, files=files)

    if response.status_code == 200:
        return response.json()['data']['link']
    else:
        return None


def create_spectrogram(file_path):
    audio = AudioSegment.from_file(file_path, format="flac")
    audio_data = audio.get_array_of_samples()

    if audio.channels == 2:
        # For stereo audio, use only the left channel
        left_channel = audio_data[::2]
        mixed_channel = np.array(left_channel)
    else:
        # For mono, simply use the audio data as is
        mixed_channel = np.array(audio_data)

    sample_rate = audio.frame_rate

    # Increase the figure size for better visibility
    plt.figure(figsize=(14, 8))
    # Use a higher NFFT to increase the frequency resolution
    NFFT = 2048  # The number of data points used in each block for the FFT
    # Use noverlap to increase the time resolution
    noverlap = NFFT // 2  # Specifies the number of points of overlap between blocks
    # Generate the spectrogram
    _, _, Sxx, im = plt.specgram(mixed_channel, Fs=sample_rate, NFFT=NFFT, noverlap=noverlap, cmap='viridis')

    plt.ylabel('Frequency (Hz)')
    plt.xlabel('Time (s)')
    plt.colorbar(im, label='Intensity dB')

    base_filename = os.path.splitext(os.path.basename(file_path))[0]
    output_image_path = f"{base_filename}_Spectrogram.png"

    plt.savefig(output_image_path)
    plt.close()

    return output_image_path, base_filename


def clear_clipboard():
    pyperclip.copy('')


def main():
    # Ensure logging is only configured once to avoid duplicating log entries
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(filename=LOG_FILENAME, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Get the folder path from the user
    folder_path = input("Enter the folder path: ").strip('\'"')

    # Extract the folder name to use as the Pastebin title
    folder_name = os.path.basename(folder_path)

    # Get the list of tracks in the folder
    track_files = [os.path.join(folder_path, file) for file in os.listdir(folder_path) if file.lower().endswith(".flac") and os.path.isfile(os.path.join(folder_path, file))]
    if not track_files:
        print("No FLAC files found in the specified folder.")
        return

    # Get audio info for the first track
    first_track_file = track_files[0]
    bitrate_kbps, sample_rate, channels, bit_depth, codec, encoding = get_audio_info(first_track_file)

    # Create spectrogram and upload to Imgur
    spectrogram_path, track_name = create_spectrogram(first_track_file)
    spectrogram_link = upload_to_imgur(spectrogram_path, IMGUR_CLIENT_ID)

    # Delete the spectrogram image from the PC
    os.remove(spectrogram_path)

    # Get bitrates for all tracks
    bitrates = [get_audio_info(track)[0] for track in track_files]

    # Replace artist names with track numbers and bitrates for all tracks
    reformatted_tracks = replace_artist_with_track_number([os.path.basename(track) for track in track_files], bitrates)
    reformatted_text = '\n'.join(reformatted_tracks)

    # Attempt Pastebin upload with reformatted text and folder name as title
    paste_url = upload_to_pastebin(PASTEBIN_API_KEY, PASTEBIN_USER_KEY, folder_name, reformatted_text)

    if paste_url:
        print(f"Reformatted tracks have been uploaded to Pastebin: {paste_url}")
        logging.info(f"Reformatted tracks uploaded to Pastebin: {paste_url}")
    else:
        print("Pastebin upload failed. Attempting to upload to Gist as a backup.")
        gist_url = upload_to_gist(GITHUB_TOKEN, folder_name, reformatted_text)
        if gist_url:
            print(f"Reformatted tracks have been uploaded to Gist: {gist_url}")
            logging.info(f"Reformatted tracks uploaded to Gist: {gist_url}")
            paste_url = gist_url  # Set paste_url to gist_url for BBCode table
        else:
            print("Gist upload failed. Clipboard will be cleared.")
            clear_clipboard()

    # Format BBCode table
    codec_display = "FLAC" if codec.lower() == "flac" else codec.upper()
    bbcode_table = f"""
    [table]
    [tr]
    [td]Spectrogram ({track_name}):[/td]
    [td][URL]{spectrogram_link}[/URL][/td]
    [/tr]
    [tr]
    [td]Sample Rate:[/td]
    [td]{sample_rate} Hz[/td]
    [/tr]
    [tr]
    [td]Channels:[/td]
    [td]{channels}[/td]
    [/tr]
    [tr]
    [td]Bitrate:[/td]
    [td]{bitrate_kbps}~ kbps (Averaged, Check Tracklist)[/td]
    [/tr]
    [tr]
    [td]Bits Per Sample[/td]
    [td]{bit_depth} Bit[/td]
    [/tr]
    [tr]
    [td]Codec:[/td]
    [td]{codec_display}[/td]
    [/tr]
    [tr]
    [td]Encoding:[/td]
    [td]{encoding.value}[/td]
    [/tr]
    [tr]
    [td]Tracklist:[/td]
    [td][url]{paste_url}[/url][/td]
    [/tr]
    [/table]
    """

    # Copy BBCode table to clipboard
    pyperclip.copy(bbcode_table)
    print("BBCode table has been copied to your clipboard.")
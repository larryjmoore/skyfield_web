# Skyfield Web Application

![Sample Sky Chart](images/sky_chart_sample.png)

This project is a Python-based web application that generates a sky chart image showing the apparent positions of the Sun, Moon, and planets. It is built using the Flask web framework and the Skyfield library for astronomical calculations. The chart is generated as a PNG image using Matplotlib.

The application is designed to be integrated with Home Assistant by setting up a [Generic Camera entity](https://www.home-assistant.io/integrations/generic/) pointing to the image URL and then display on your dashboard using a Picture entity, but can also function as a standalone service as well. Please set the refresh rate to something reasonable, like 0.0033 Hz (every 5 minutes).

If you would rather use my setup directly, you can access it now via https://skyfieldweb.duckdns.org/skychart.png. Make sure to see below for how to customize the URL for your setup.

## Features

*   Displays apparent positions of the Sun, Moon, and planets.
*   Generates sky charts as PNG images.
*   Customizable with latitude, longitude, elevation, and timezone.
*   Option to show analemma, constellations, and planets.

## Project Structure

*   `__init__.py`: Package initialization.
*   `app.py`: The main Flask application.
*   `bodies.py`: Contains logic for celestial body calculations and plotting.
*   `constellations.py`: Handles drawing constellations.
*   `__main__.py`: Allows the package to be run as a module.
*   `data/`: Directory for astronomical data files (e.g., `de421.bsp`).
*   `tests/`: Directory for unit and integration tests.
*   `venv/`: Python virtual environment.
*   `pyproject.toml`: Project metadata and dependencies.
*   `requirements.txt`: Python dependency list.
*   `LICENSE`: Project license.
*   `.gitignore`: Specifies files and directories to be ignored by Git.

## Setup and Running

### Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)

### 1. Clone the repository

```bash
git clone https://github.com/larryjmoore/skyfield_web
cd skyfield_web
```

### 2. Create and activate a virtual environment

It is highly recommended to use a virtual environment to manage project dependencies.

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -e .
```

This command installs the project in editable mode, making the `skyfield_web` package available.

### 4. Download astronomical data

The application requires astronomical ephemeris data. This will be downloaded automatically the first time the application runs and stored in the `data/` directory. Ensure you have an active internet connection the first time you run it.

### 5. Run the application

To start the Flask development server:

```bash
python3 -m skyfield_web
```

This will start the server on `http://0.0.0.0:8000`.

### 6. Access the Sky Chart

Open your web browser and navigate to:

```
http://localhost:8000/skychart.png
```

You can customize the chart by providing query parameters:

*   `lat`: Latitude (e.g., `34.0522`)
*   `lon`: Longitude (e.g., `-118.2437`)
*   `elevation`: Elevation in meters (e.g., `1447`)
*   `timezone`: IANA Time Zone Database name (e.g., `America/Los_Angeles`)
*   `show_analemma`: `true` or `false` (default: `false`)
*   `show_constellation`: `true` or `false` (default: `false`)
*   `show_planets`: `true` or `false` (default: `true`)
*   `north_up`: `true` or `false` (default: `false`)
*   `show_time`: `true` or `false` (default: `true`)
*   `show_legend`: `true` or `false` (default: `true`)
*   `show_stats`: `true` or `false` (default: `true`) - Shows/hides all extra statistics (twilight, solar noon, next event, moon info).

Optional overrides to force a specific day and time:

*   `year`: Year (e.g., `2026`)
*   `month`: Month (e.g., `1` for January)
*   `day`: Day (e.g., `15`)
*   `hour`: Hour (24-hour format, e.g., `14` for 2 PM)
*   `minute`: Minute (e.g., `30`)
*   `second`: Second (e.g., `0`)

    *Note: All of the `year`, `month`, `day`, `hour`, `minute`, and `second` parameters
must be provided for the custom time to be applied. Otherwise, the current time will be used.* 

Example:

```
http://localhost:8000/skychart.png?lat=34.0522&lon=-118.2437&timezone=America/Los_Angeles&show_constellation=true
```

## License

This project is licensed under the GNU General Public License v3.0. See the `LICENSE` file for details.

## Acknowledgements

This project was inspired by and adapted from the [ha_skyfield](https://github.com/partofthething/ha_skyfield) repository by @partofthething.
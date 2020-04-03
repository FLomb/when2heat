
# %%
# Python modules
import os
import shutil
import pandas as pd
from time import time
from datetime import date

# Custom scripts
import scripts.download as download 
import scripts.read as read
import scripts.preprocess as preprocess
import scripts.demand as demand
import scripts.cop as cop
import scripts.write as write
import scripts.metadata as metadata

# get_ipython().run_line_magic('load_ext', 'autoreload')
# get_ipython().run_line_magic('autoreload', '2')
# get_ipython().run_line_magic('matplotlib', 'inline')

# %%
version = '2019-08-06'
changes = 'Minor revisions'

# %% [markdown]
# ## Make directories

# %%
home_path = os.path.realpath('.')

input_path = os.path.join(home_path, 'input')
interim_path = os.path.join(home_path, 'interim')
output_path = os.path.join(home_path, 'output', version)

for path in [input_path, interim_path, output_path]:
    os.makedirs(path, exist_ok=True)

# %% [markdown]
# ## Select geographical and temporal scope

# %%
all_countries = ['AT'] # available
regions = read.shapes(input_path)
regions = regions.loc[regions.country_code.isin(all_countries)]

# %%
year_start = 2008
year_end = 2009

# %% [markdown]
# ## Set ECMWF access key
# In the following, this notebook downloads weather data from the ECMWF server. For accessing this server, follow the steps below:
# 1.  Register at https://apps.ecmwf.int/registration/.
# 2.  Login at https://apps.ecmwf.int/auth/login/.
# 3.  Retrieve your key at https://api.ecmwf.int/v1/key/.
# 4.  Enter your key and your e-mail below.
# 
# If you have already [installed](https://confluence.ecmwf.int/display/WEBAPI/Access+ECMWF+Public+Datasets#AccessECMWFPublicDatasets-key) your ECMWF KEY, this step is skipped.

# %%
if not os.path.isfile(os.path.join(os.environ['USERPROFILE'], ".ecmwfapirc")):
    os.environ["ECMWF_API_URL"] = "https://api.ecmwf.int/v1"
    os.environ["ECMWF_API_KEY"] = "d48ab4f9f66533f9015eaa5472c4a807"
    os.environ["ECMWF_API_EMAIL"] = "francesco.lombardi@polimi.it"


# %% [markdown]
# <a id=download></a>
# # 2. Download
# In the following, weather and population data is downloaded from the respective sources. For all years and countries, this takes around 45 minutes to run.
# 
# Note that standard load profile parameters from [BGW](http://www.gwb-netz.de/wa_files/05_bgw_leitfaden_lastprofile_56550.pdf)/[BDEW](https://www.enwg-veroeffentlichungen.de/badtoelz/Netze/Gasnetz/Netzbeschreibung/LF-Abwicklung-von-Standardlastprofilen-Gas-20110630-final.pdf) and energy statistics from the [EU Builidng Database](http://ec.europa.eu/energy/en/eu-buildings-database) are already provided with this notebook in the input directory.
# %% [markdown]
# ## Weather data
# As mentioned above, weather data is downloaded from ECMWF, more specifically form the [ERA-Interim](https://www.ecmwf.int/en/research/climate-reanalysis/era-interim) archive. The following data is retrieved:
# * Wind: wind speed at 10 m above ground for heating seasons (October-April) in 1979-2016 in monthly resolution 
# * Temperature: ambient air temperature at 2 m above ground for the selected years in six-hourly resolution 
# 
# All data is downloaded for the whole of Europe. If some data already exists on your computer, this data will be skipped in the download process.

# %%
download.wind(input_path)
# %%
download.temperatures(input_path, year_start, year_end)

# %% [markdown]
# ## Population data
# As mentioned above, population data is downloaded from [EUROSTAT](http://ec.europa.eu/eurostat/web/gisco/geodata/reference-data/population-distribution-demography/geostat).

# %%
download.population(input_path)

# %% [markdown]
# <a id=pre></a>
# # 3. Preprocessing
# Population and weather data is preprocessed. This takes around 10 minutes to run.
# %% [markdown]
# ## Re-mapping population data
# The population data from Eurostat features a 1 km² grid, which country-by-country transformed to the 0.75 x 0.75° grid of the weather data in the following. Interim results are saved/loaded from disk.

# %%
mapped_population = preprocess.map_population(input_path, regions, interim_path)


# %%
mapped_population['AT']

# %% [markdown]
# ## Preparing weather data
# 
# The temporal resolution of the weather data is changed as follows:
# * Temperatures (air and soil): from six-hours to one hour
# * Wind: from monthly to the average of all heating periods from 1979 to 2016
# 
# To speed up the calculation, all weather data is filtered by the selected countries.

# %%
wind = preprocess.wind(input_path, mapped_population)


# %%
temperature = preprocess.temperature(input_path, year_start, year_end, mapped_population)

# %% [markdown]
# <a id=demand></a>
# # 4. Heat demand time series
# For all years and countries, the calculation of heat demand time series takes around 20 minutes to run.
# %% [markdown]
# ## Reference temperature
# 
# To capture the thermal inertia of buildings, the daily reference temperature is calculated as the weighted mean of the ambient air temperature of the actual and the three preceding days. 

# %%
reference_temperature = demand.reference_temperature(temperature['air'])

# %% [markdown]
# ## Daily demand
# 
# Daily demand factors are derived from the reference temperatures using profile functions as described in [BDEW](https://www.enwg-veroeffentlichungen.de/badtoelz/Netze/Gasnetz/Netzbeschreibung/LF-Abwicklung-von-Standardlastprofilen-Gas-20110630-final.pdf).

# %%
daily_parameters = read.daily_parameters(input_path)


# %%
daily_heat = demand.daily_heat(reference_temperature, 
                               wind, 
                               daily_parameters)


# %%
daily_water = demand.daily_water(reference_temperature,
                                 wind,
                                 daily_parameters)

# %% [markdown]
# ## Hourly demand
# 
# Hourly damand factors are calculated from the daily demand based on hourly factors from [BGW](http://www.gwb-netz.de/wa_files/05_bgw_leitfaden_lastprofile_56550.pdf).

# %%
hourly_parameters = read.hourly_parameters(input_path)


# %%
hourly_heat = demand.hourly_heat(daily_heat,
                                 reference_temperature, 
                                 hourly_parameters)


# %%
hourly_water = demand.hourly_water(daily_water,
                                   reference_temperature, 
                                   hourly_parameters)


# %%
hourly_space = (hourly_heat - hourly_water).clip(lower=0)

# %% [markdown]
# ## Weight and scale
# The spatial time series are weighted with the population and normalized to 1 TWh yearly demand each. Years included in the building database are scaled accordingly. The time series not spatially aggregated yet because spatial time series are needed for COP calculation.

# %%
building_database = read.building_database(input_path)


# %%
spatial_space = demand.finishing(hourly_space, mapped_population, building_database['space'])


# %%
spatial_water = demand.finishing(hourly_water, mapped_population, building_database['water'])

# %% [markdown]
# ## Safepoint
# 
# The following cells can be used to save and reload the spatial hourly time series.

# %%
spatial_space.to_pickle(os.path.join(interim_path, 'spatial_space'))
spatial_water.to_pickle(os.path.join(interim_path, 'spatial_water'))


# %%
spatial_space = pd.read_pickle(os.path.join(interim_path, 'spatial_space'))[countries]
spatial_water = pd.read_pickle(os.path.join(interim_path, 'spatial_water'))[countries]

# %% [markdown]
# ## Aggregate and combine
# All heat demand time series are aggregated country-wise and combined into one data frame.

# %%
final_heat = demand.combine(spatial_space, spatial_water)

# %% [markdown]
# <a id=cop></a>
# # 5. COP time series
# For all years and countries, the calculation of the coefficient of performance (COP) of heat pumps takes around 5 minutes to run.
# %% [markdown]
# ## Source temperature 
# For air-sourced, ground-sources and groundwater-sourced heat pumps (ASHP, GSHP and WSHP), the relevant heat source temperatures are calculated.

# %%
source_temperature = cop.source_temperature(temperature)

# %% [markdown]
# ## Sink temperatures
# Heat sink temperatures, i.e. the temperature level at which the heat pumps have to provide heat, are calculated for floor heating, radiator heating and warm water.

# %%
sink_temperature = cop.sink_temperature(temperature)

# %% [markdown]
# ## COP
# The COP is derived from the temperature difference between heat sources and sinks using COP curves.

# %%
cop_parameters = read.cop_parameters(input_path)


# %%
spatial_cop = cop.spatial_cop(source_temperature, sink_temperature, cop_parameters)

# %% [markdown]
# ## Safepoint
# 
# The following cells can be used to save and reload the spatial hourly time series.

# %%
spatial_cop.to_pickle(os.path.join(interim_path, 'spatial_cop'))


# %%
spatial_cop = pd.read_pickle(os.path.join(interim_path, 'spatial_cop'))[countries]

# %% [markdown]
# ## Aggregating and correction
# The spatial COP time series are weighted with the spatial heat demand and aggregated into national time series. The national time series are corrected for part-load losses.

# %%
final_cop = cop.finishing(spatial_cop, spatial_space, spatial_water)

# %% [markdown]
# ## COP averages
# COP averages (performance factors) are calculated and saved to disk for validation purposes.

# %%
cop.validation(final_cop, final_heat, interim_path, 'corrected')


# %%
cop.validation(cop.finishing(spatial_cop, spatial_space, spatial_water, correction=1),
               final_heat, interim_path, "uncorrected")

# %% [markdown]
# <a id=write></a>
# # 6. Writing
# For data and metadata, this takes around 5 minutes to run.
# %% [markdown]
# ## Data
# As for the OPSD "Time Series" package, data are provided in three different "shapes":
# 
# * SingleIndex (easy to read for humans, compatible with datapackage standard, small file size)
#   * Fileformat: CSV, SQLite
# * MultiIndex (easy to read into GAMS, not compatible with datapackage standard, small file size)
#   * Fileformat: CSV, Excel
# * Stacked (compatible with data package standard, large file size, many rows, too many for Excel)
#   * Fileformat: CSV
# %% [markdown]
# The different shapes are created before they are saved to files.

# %%
shaped_dfs = write.shaping(final_heat, final_cop)

# %% [markdown]
# Write data to an SQL-database, ...

# %%
write.to_sql(shaped_dfs, output_path, home_path)

# %% [markdown]
# and to CSV.

# %%
write.to_csv(shaped_dfs, output_path)

# %% [markdown]
# Writing to Excel takes extremely long. As a workaround, a copy of the multi-indexed data is writtten to CSV and manually converted to Excel.
# %% [markdown]
# ## Metadata
# The metadata is reported in a JSON file.

# %%
metadata.make_json(shaped_dfs, version, changes, year_start, year_end, output_path)

# %% [markdown]
# ## Copy input data

# %%
shutil.copytree(input_path, os.path.join(output_path, 'original_data'))

# %% [markdown]
# ## Checksums

# %%
metadata.checksums(output_path, home_path)


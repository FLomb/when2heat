
import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

import scripts.read as read
from scripts.misc import upsample_df


def map_population(input_path, regions, interim_path, plot=True):

    mapped_population = {}

    population = read.population(input_path)
    weather_data = read.wind(input_path)  # For the weather grid

    # Make GeoDataFrame from the weather data coordinates
    weather_grid = gpd.GeoDataFrame(index=weather_data.columns)
    weather_grid['geometry'] = weather_grid.index.map(lambda i: Point(reversed(i)))

    # Set coordinate reference system to 'latitude/longitude'
    weather_grid.crs = {'init': 'epsg:4326'}

    # Make polygons around the weather points
    weather_grid['geometry'] = weather_grid.geometry.apply(lambda point: point.buffer(.75 / 2, cap_style=3))

    # Make list from MultiIndex (this is necessary for the spatial join)
    weather_grid.index = weather_grid.index.tolist()

    for region in regions.iterrows():
        print(region[1].id)
        file = os.path.join(interim_path, 'population_{}'.format(region[1].id))

        if not os.path.isfile(file):
            # For Luxembourg, a single weather grid point is manually added for lack of population geodata
            if region[1].id == 'LU':
                s = pd.Series({(49.5, 6): 1})

            else:
                # Filter population data by country to cut processing time
                if region[1].id == 'GB':
                    gdf = population[population.CNTR_CODE == 'UK'].copy()
                else:
                    gdf = population[population.CNTR_CODE == region[1].country_code].copy()

                # Align coordinate reference systems
                gdf = gdf.to_crs({'init': 'epsg:4326'})
                print(gdf)

                # Spatial join, first to the region, then to the weather grid points
                region_points = gpd.sjoin(
                    gdf, regions.loc[[region[0]]], how="left", op='within'
                )
                weather_grid_points = gpd.sjoin(
                    region_points.dropna().drop('index_right', axis=1),
                    weather_grid, how="left", op='within'
                )


                # Sum up population
                s = weather_grid_points.groupby('index_right')['TOT_P'].sum()

            # Write results to interim path
            s.to_pickle(file)

        else:

            s = pd.read_pickle(file)
            print('{} already exists and is read from disk.'.format(file))

        mapped_population[region[1].id] = s

    if plot:
        print('Plot of the re-mapped population data of {} (first selected country) '
              'for visual inspection:'.format(regions.id.values[0]))
        gdf = gpd.GeoDataFrame(mapped_population[regions.id.values[0]], columns=['TOT_P'])
        gdf['geometry'] = gdf.index.map(lambda i: Point(reversed(i)))
        gdf.plot(column='TOT_P')

    return mapped_population


def wind(input_path, mapped_population, plot=True):

    df = read.wind(input_path)

    # Temporal average
    s = df.mean(0)

    if plot:
        print('Plot of the wind averages for visual inspection:')
        gdf = gpd.GeoDataFrame(s, columns=['wind'])
        gdf['geometry'] = gdf.index.map(lambda i: Point(reversed(i)))
        gdf.plot(column='wind')

    # Wind data is filtered by country
    return pd.concat(
        [s[population.index] for population in mapped_population.values()],
        keys=mapped_population.keys(), names=['country', 'latitude', 'longitude'], axis=0
    ).apply(pd.to_numeric, downcast='float')


def temperature(input_path, year_start, year_end, mapped_population):

    parameters = {
        'air': 't2m',
        'soil': 'stl4'
    }

    t = pd.concat(
        [read.temperature(input_path, year_start, year_end, parameter) for parameter in parameters.values()],
        keys=parameters.keys(), names=['parameter', 'latitude', 'longitude'], axis=1
    )

    t = upsample_df(t, '60min')

    # Temperature data is filtered by country
    return pd.concat(
        [pd.concat(
            [t[parameter][population.index] for population in mapped_population.values()],
            keys=mapped_population.keys(), axis=1
        ) for parameter in parameters.keys()],
        keys=parameters.keys(), names=['parameter', 'country', 'latitude', 'longitude'], axis=1
    ).apply(pd.to_numeric, downcast='float')

#%% Custom temperature

# def upsample_df(df, resolution):

#     # The low-resolution values are applied to all high-resolution values up to the next low-resolution value
#     # In particular, the last low-resolution value is extended up to where the next low-resolution value would be

#     df = df.copy()

#     # Determine the original frequency
#     freq = df.index[-1] - df.index[-2]

#     # Temporally append the DataFrame by one low-resolution value
#     df.loc[df.index[-1] + freq, :] = df.iloc[-1, :]

#     dtidx = pd.date_range(str(df.index[0]),str(df.index[-1]), freq=freq)
#     df.index = dtidx

#     # Up-sample
#     df = df.resample(resolution).pad()

#     # Drop the temporal low-resolution value
#     df.drop(df.index[-1], inplace=True)

#     return df

# parameters = {
#     'air': 't2m',
#     'soil': 'stl4'
# }

# t = pd.concat(
#     [read.temperature(input_path, year_start, year_end, parameter) for parameter in parameters.values()],
#     keys=parameters.keys(), names=['parameter', 'latitude', 'longitude'], axis=1
# )

# t = upsample_df(t, '60min')

# # Temperature data is filtered by country
# temperature = pd.concat(
#     [pd.concat(
#         [t[parameter][population.index] for population in mapped_population.values()],
#         keys=mapped_population.keys(), axis=1
#     ) for parameter in parameters.keys()],
#     keys=parameters.keys(), names=['parameter', 'country', 'latitude', 'longitude'], axis=1
# ).apply(pd.to_numeric, downcast='float')
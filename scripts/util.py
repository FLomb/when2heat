import shapely
import requests
import zipfile
import io

import geopandas as gpd
import pandas as pd
import numpy as np
import cartopy
import pycountry


def get_nuts(year):
    print('Getting NUTS data for year {}'.format(year))
    nuts3 = gpd.read_file(
        'https://ec.europa.eu/eurostat/cache/GISCO/distribution/v2/nuts/geojson/NUTS_RG_10M_{}_3035_LEVL_3.geojson'
        .format(year)
    )
    nuts3.set_index('id', inplace=True)
    nuts3 = nuts3.to_crs('epsg:4326')
    return nuts3


def combine_nuts_ehighways(nuts_gdf, ehighways_df):
    ehighways_df = ehighways_df.reset_index()
    nuts3 = ehighways_df.loc[ehighways_df.Source == 'NUTS3'].set_index('NUTS3')
    nuts0 = ehighways_df.loc[(ehighways_df.Source == 'NUTS0')].set_index('Country')
    gadm0 = ehighways_df.loc[(ehighways_df.Source == 'GADM')].set_index('e-Highway cluster')

    # Map anything with direct reference to a NUTS3 region
    nuts_gdf['ehighways'] = nuts3.reindex(nuts_gdf.index)['e-Highway cluster'].values

    # Map ehighways clusters which refer to entire countries
    whole_country = nuts_gdf.loc[nuts_gdf.CNTR_CODE.isin(nuts0.index)]
    nuts_gdf.loc[whole_country.index, 'ehighways'] = (
        nuts0.reindex(whole_country.set_index('CNTR_CODE').index)['e-Highway cluster'].values
    )

    # There are some countries that have no NUTS shapefiles, so we instead get them from GADM
    for i in gadm0.iterrows():
        # Kosovo is seperated from serbia in GADM, so we re-attach them (sorry Kosovo...)
        if i[1].Country == 'XK':
            gadm_shp = get_gadm('65_RS', country='XK', alpha3='XKO')
        else:
            gadm_shp = get_gadm(i[0])
        nuts_gdf = nuts_gdf.append(gadm_shp, sort=True)

    return nuts_gdf


def get_gadm(ehighway_code, country=None, alpha3=None):
    """
    Download and extract gadm shapefiles for a specific country.
    Keep only whole-country (GADM0) shape, and update it to match NUTS gdf column naming
    """
    if country is None:
        country = ehighway_code.split('_')[1].upper()
    alpha2 = pycountry.countries.get(alpha_2=country)
    if alpha3 is None:
        alpha3 = alpha2.alpha_3
    url =' https://biogeo.ucdavis.edu/data/gadm3.6/shp/gadm36_{}_shp.zip'.format(alpha3)

    local_path = 'tmp/'
    print('Downloading GADM shapefile for {}...'.format(country))
    r = requests.get(url)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(path=local_path) # extract to folder
    shp = gpd.read_file(local_path + 'gadm36_{}_0.shp'.format(alpha3))
    shp = shp.to_crs('epsg:4326')
    shp = (
        shp.rename({'NAME_0': 'NUTS_NAME'}, axis=1)
           .rename({0: '{}001'.format(country)}, axis=0)
           .drop('GID_0', axis=1)
           .assign(
                CNTR_CODE=country,
                LEVL_CODE=np.nan,
                FID=np.nan,
                NUTS_ID=np.nan,
                ehighways=ehighway_code
            )
    )
    return shp
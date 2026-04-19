import os
import json
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc

# ── Rutas ──────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, 'data')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')

# ── Paleta ─────────────────────────────────────────────────────────────────────
C_PRIMARY   = '#0c71e3'
C_DARK      = '#003893'
C_DARKEST   = '#17365d'
C_CYAN      = '#02c3ec'
C_PURPLE    = '#7030a0'
C_PURPLE_LT = '#C3a5fb'
C_LAVENDER  = '#d5d5ff'
C_YELLOW    = '#FFde59'
C_RED       = '#ff1616'
C_GREEN     = '#2ecc71'
C_ORANGE    = '#f39c12'
C_TEAL      = '#1abc9c'
C_GRAY      = '#95a5a6'
C_WHITE     = '#FFFFFF'

COLORSCALE_COUNT = [[0, '#e8f1fd'], [0.5, C_PRIMARY], [1, C_DARKEST]]
COLORSCALE_RATE  = [[0, '#fef9e7'], [0.5, C_ORANGE],  [1, C_RED]]

FILTER_LABEL = {'fontSize': '0.75rem', 'fontWeight': 600,
                'color': C_DARKEST, 'marginBottom': '4px'}

INFO_STYLE = {
    'backgroundColor': '#dbeeff',
    'borderRadius': '8px',
    'padding': '16px 20px',
    'fontSize': '0.85rem',
    'color': C_DARKEST,
    'lineHeight': '1.6',
}

# ── Grupos de delito ────────────────────────────────────────────────────────────
GRUPO_MAP = {
    'ESCNNA':            ['DELITOS SEXUALES'],
    'Trata de Personas': ['TRATA DE PERSONAS', 'LIBERTAD INDIVIDUAL Y OTRAS GARANTIAS'],
}
GRUPOS = list(GRUPO_MAP.keys())

# ── Etapas de caso ──────────────────────────────────────────────────────────────
ETAPA_COLORS = {
    'INDAGACIÓN':             C_GRAY,
    'INVESTIGACIÓN':          C_CYAN,
    'JUICIO':                 C_PRIMARY,
    'TERMINACIÓN ANTICIPADA': C_GREEN,
    'EJECUCIÓN DE PENAS':     C_DARK,
}

# ── Datos ──────────────────────────────────────────────────────────────────────
df = pd.read_csv(os.path.join(DATA_DIR, 'victimas.csv'),
                 encoding='utf-8-sig', dtype={'cod_dep': str, 'cod_mun': str})
df_dep_pop = pd.read_csv(os.path.join(DATA_DIR, 'poblacion_depto.csv'),
                         encoding='utf-8-sig', dtype={'cod_dep': str})
df_mun_pop = pd.read_csv(os.path.join(DATA_DIR, 'poblacion_mpio.csv'),
                         encoding='utf-8-sig', dtype={'cod_dep': str, 'cod_mun': str})

df['anio_denuncia']      = pd.to_numeric(df['anio_denuncia'],      errors='coerce')
df['total_victimas']     = pd.to_numeric(df['total_victimas'],     errors='coerce').fillna(0).astype(int)
df['total_victimas_nna'] = pd.to_numeric(df['total_victimas_nna'], errors='coerce').fillna(0).astype(int)

with open(os.path.join(ASSETS_DIR, 'geojson', 'departamentos.geojson'), encoding='utf-8') as f:
    geojson_dep = json.load(f)
with open(os.path.join(ASSETS_DIR, 'geojson', 'municipios.geojson'), encoding='utf-8') as f:
    geojson_mun = json.load(f)

YEARS          = sorted(df['anio_denuncia'].dropna().astype(int).unique().tolist())
YEAR_MIN, YEAR_MAX = YEARS[0], YEARS[-1]
DEPTOS         = sorted(df['departamento_hecho'].dropna().unique().tolist())
DELITOS        = sorted(df['delito'].dropna().unique().tolist())
POP_NATIONAL   = df_dep_pop.groupby('AÑO', as_index=False)['Total'].sum()


def _geo_bounds(geojson, pad=0.04):
    """Calcula lat/lon min-max de un GeoJSON para fijar la vista del mapa."""
    lats, lons = [], []
    for feat in geojson.get('features', []):
        geom = feat.get('geometry', {})
        gtype = geom.get('type', '')
        coords = geom.get('coordinates', [])
        rings = coords if gtype == 'MultiPolygon' else [coords]
        for poly in rings:
            for ring in poly:
                for pt in ring:
                    lons.append(pt[0]); lats.append(pt[1])
    if not lats:
        return None
    lat_r = max(lats) - min(lats)
    lon_r = max(lons) - min(lons)
    return dict(
        lat=[min(lats) - lat_r * pad, max(lats) + lat_r * pad],
        lon=[min(lons) - lon_r * pad, max(lons) + lon_r * pad],
    )


# Bounds precalculados al inicio (se usan en todos los callbacks)
_DEP_BOUNDS = _geo_bounds(geojson_dep)
_MUN_BOUNDS = _geo_bounds(geojson_mun)
_DEP_MUN_BOUNDS = {
    d: _geo_bounds({'type': 'FeatureCollection',
                    'features': [f for f in geojson_mun['features']
                                 if f['properties']['departamento'] == d]})
    for d in DEPTOS
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def _grupo_delitos(grupos):
    if not grupos:
        return []
    g_list = [grupos] if isinstance(grupos, str) else grupos
    actual = []
    for g in g_list:
        actual.extend(GRUPO_MAP.get(g, [g]))
    return actual


def filter_df(anios, grupos, depto, delitos):
    mask = pd.Series(True, index=df.index)
    if anios:
        mask &= df['anio_denuncia'].between(anios[0], anios[1])
    actual = _grupo_delitos(grupos)
    if actual:
        mask &= df['grupo_delito'].isin(actual)
    if depto and depto != 'Todos':
        mask &= df['departamento_hecho'] == depto
    if delitos:
        mask &= df['delito'].isin(delitos)
    return df[mask].copy()


def filter_df_no_year(grupos, depto, delitos):
    mask = pd.Series(True, index=df.index)
    actual = _grupo_delitos(grupos)
    if actual:
        mask &= df['grupo_delito'].isin(actual)
    if depto and depto != 'Todos':
        mask &= df['departamento_hecho'] == depto
    if delitos:
        mask &= df['delito'].isin(delitos)
    return df[mask].copy()


def apply_layout(fig, height=320, title='', legend_bottom=False, **extra):
    """
    legend_bottom=True: leyenda horizontal debajo del gráfico (mayor margen inferior).
    """
    t_margin = 52 if title else 20
    b_margin = 55 if legend_bottom else 15
    args = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Inter, Arial, sans-serif', color=C_DARKEST),
        margin=dict(l=10, r=10, t=t_margin, b=b_margin),
        height=height,
        legend=dict(orientation='h', y=-0.18, x=0.5, xanchor='center',
                    bgcolor='rgba(0,0,0,0)', font=dict(size=11))
               if legend_bottom else dict(bgcolor='rgba(0,0,0,0)'),
    )
    if title:
        args['title'] = dict(
            text=f'<b>{title}</b>',
            font=dict(size=20, color=C_DARK),
            x=0, pad=dict(l=4),
        )
    args.update(extra)
    fig.update_layout(**args)


def empty_fig(msg='Sin datos', height=320):
    fig = go.Figure()
    fig.add_annotation(text=msg, xref='paper', yref='paper',
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=13, color=C_GRAY))
    apply_layout(fig, height)
    return fig


def kpi_card(title, value, color=C_PRIMARY, subtitle=''):
    return dbc.Card([
        dbc.CardBody([
            html.P(title, className='text-muted mb-2',
                   style={'fontSize': '1rem', 'fontWeight': 600,
                          'textAlign': 'center'}),
            html.H1(f'{value:,}',
                    style={'color': color, 'fontWeight': 700, 'margin': 0,
                           'fontSize': '2.6rem', 'textAlign': 'center'}),
            html.P(subtitle,
                   style={'fontSize': '0.82rem', 'color': C_GRAY,
                          'margin': '6px 0 0 0', 'textAlign': 'center'})
            if subtitle else None,
        ], style={
            'display': 'flex', 'flexDirection': 'column',
            'justifyContent': 'center', 'alignItems': 'center',
            'height': '100%',
        })
    ], className='shadow-sm border-0 h-100')


def rank_table(rows, col1='Territorio', col2='Valor', max_height='470px'):
    th_style = {
        'position': 'sticky', 'top': 0,
        'backgroundColor': C_DARKEST, 'color': C_WHITE,
        'padding': '6px 10px', 'fontSize': '0.74rem',
        'fontWeight': 600, 'textAlign': 'left',
    }
    th_r = {**th_style, 'textAlign': 'right'}
    td_style = {'padding': '4px 10px', 'fontSize': '0.78rem',
                'borderBottom': '1px solid #eef0f2'}
    td_r = {**td_style, 'textAlign': 'right', 'fontWeight': 600, 'color': C_PRIMARY}

    body = [
        html.Tr([
            html.Td(name, style={**td_style,
                                  'backgroundColor': '#ffffff' if i % 2 == 0 else '#f8faff'}),
            html.Td(val,  style={**td_r,
                                  'backgroundColor': '#ffffff' if i % 2 == 0 else '#f8faff'}),
        ])
        for i, (name, val) in enumerate(rows)
    ]
    return html.Div(
        html.Table(
            [html.Thead(html.Tr([html.Th(col1, style=th_style),
                                  html.Th(col2, style=th_r)])),
             html.Tbody(body)],
            style={'width': '100%', 'borderCollapse': 'collapse'},
        ),
        style={'maxHeight': max_height, 'overflowY': 'auto',
               'border': '1px solid #dee2e6', 'borderRadius': '6px'}
    )


def section_title(text):
    return html.Div([
        html.H2(text, style={'color': C_DARKEST, 'fontWeight': 700,
                              'margin': 0, 'fontSize': '1.9rem',
                              'textAlign': 'center'}),
        html.Hr(style={'borderColor': C_PRIMARY, 'borderWidth': '3px',
                        'marginTop': '10px', 'marginBottom': '20px'}),
    ], style={'marginTop': '36px'})


# ── App ────────────────────────────────────────────────────────────────────────
app = Dash(__name__,
           external_stylesheets=[dbc.themes.BOOTSTRAP],
           assets_folder=ASSETS_DIR,
           suppress_callback_exceptions=True)
server = app.server

# ── Layout ────────────────────────────────────────────────────────────────────
app.layout = dbc.Container(fluid=True,
    style={'backgroundColor': '#f4f7fb', 'minHeight': '100vh', 'paddingBottom': '40px'},
    children=[

    # ── Header ───────────────────────────────────────────────────────────────
    dbc.Row(dbc.Col(html.Div([
        html.H1('Aplicativo de Cifras sobre ESCNNA y Trata con NNA en Colombia',
                style={'color': C_WHITE, 'fontWeight': 700, 'margin': 0,
                       'fontSize': '2.2rem', 'textAlign': 'center'}),
        html.P('Observatorio ESCNNA-Valientes Colombia',
               style={'color': C_LAVENDER, 'margin': '10px 0 0 0',
                      'fontSize': '1.05rem', 'textAlign': 'center'}),
    ], style={'backgroundColor': C_DARKEST, 'padding': '22px 24px'})),
    className='mb-3'),

    # ── Texto explicativo general ─────────────────────────────────────────────
    dbc.Row(dbc.Col(html.Div([
        html.P([
            html.Strong('La explotación sexual comercial de niñas, niños y adolescentes (ESCNNA) '),
            'es una vulneración de los derechos que se materializa mediante la utilización del cuerpo, '
            'imágenes o representación de una niña, niño o adolescente con fines sexuales. Es considerado '
            'el peor delito que existe contra la niñez y adolescencia. Se presenta en diferentes modalidades '
            'y contextos y está compuesto por diferentes delitos y actos ilícitos cometidos contra personas '
            'menores de 18 años.',
        ], className='mb-2'),
        html.P([
            html.Strong('La trata de personas en Colombia '),
            'es un delito que involucra una serie de verbos rectores relacionados con el reclutamiento, '
            'transporte, acogida o recepción de personas con el propósito de explotarlas. Estos verbos '
            'rectores son acciones clave que se llevan a cabo en diferentes modalidades de trata de personas, '
            'como la explotación sexual, laboral, la servidumbre involuntaria, la esclavitud, la extracción '
            'de órganos y otras formas de explotación.',
        ], className='mb-2'),
        html.P([
            html.Strong('* '),
            'Esta herramienta contiene información de los delitos relacionados con la ESCNNA y Trata con '
            'Niños, Niñas y Adolescentes almacenada en la base de datos del Sistema Penal Oral Acusatorio (SPOA)',
        ], className='mb-0', style={'fontWeight': 500}),
    ], style=INFO_STYLE)), className='mb-3'),

    # ── Filtros ───────────────────────────────────────────────────────────────
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label('Año de denuncia', style=FILTER_LABEL),
            dcc.RangeSlider(
                id='f-anio', min=YEAR_MIN, max=YEAR_MAX,
                value=[YEAR_MIN, YEAR_MAX], step=1,
                marks={y: str(y) for y in YEARS[::3]},
                tooltip={'placement': 'bottom', 'always_visible': False},
            ),
        ], md=4),
        dbc.Col([
            html.Label('Grupo de delito', style=FILTER_LABEL),
            dcc.Dropdown(id='f-grupo',
                options=[{'label': g, 'value': g} for g in GRUPOS],
                value='ESCNNA', clearable=False, style={'fontSize': '0.83rem'}),
        ], md=2),
        dbc.Col([
            html.Label('Departamento', style=FILTER_LABEL),
            dcc.Dropdown(id='f-depto',
                options=[{'label': 'Todos', 'value': 'Todos'}] +
                        [{'label': d, 'value': d} for d in DEPTOS],
                value='Todos', clearable=False, style={'fontSize': '0.83rem'}),
        ], md=2),
        dbc.Col([
            html.Label('Delito', style=FILTER_LABEL),
            dcc.Dropdown(id='f-delito',
                options=[{'label': d, 'value': d} for d in DELITOS],
                multi=True, placeholder='Todos', style={'fontSize': '0.83rem'}),
        ], md=4),
    ])), className='shadow-sm border-0 mb-2'),

    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN: CASOS Y VÍCTIMAS
    # ══════════════════════════════════════════════════════════════════════════
    section_title('Casos y Víctimas'),

    # Histórico + KPIs
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody(
            dcc.Graph(id='chart-historico', config={'displayModeBar': False})
        ), className='shadow-sm border-0 h-100'), md=10),
        dbc.Col([
            html.Div(id='kpi-casos',    className='mb-2 h-50',
                     style={'display': 'flex', 'flexDirection': 'column'}),
            html.Div(id='kpi-victimas', className='h-50',
                     style={'display': 'flex', 'flexDirection': 'column'}),
        ], md=2, className='d-flex flex-column'),
    ], className='mb-3 g-2'),

    # Mapa departamentos + tabla
    dbc.Card(dbc.CardBody(
        dbc.Row([
            dbc.Col(dcc.Graph(id='map-dep-count', config={'displayModeBar': False}), md=8),
            dbc.Col([
                html.P('Víctimas por departamento', style={**FILTER_LABEL, 'marginBottom': '8px'}),
                html.Div(id='table-dep-count'),
            ], md=4, style={'paddingTop': '12px'}),
        ], className='g-2')
    ), className='shadow-sm border-0 mb-3'),

    # Mapa municipios + top 20
    dbc.Card(dbc.CardBody(
        dbc.Row([
            dbc.Col(dcc.Graph(id='map-mun-count', config={'displayModeBar': False}), md=8),
            dbc.Col([
                html.P('Top 20 municipios por víctimas', style={**FILTER_LABEL, 'marginBottom': '8px'}),
                html.Div(id='table-mun-count'),
            ], md=4, style={'paddingTop': '12px'}),
        ], className='g-2')
    ), className='shadow-sm border-0 mb-3'),

    # Sexo · Edad · Diversidad sexual · Diversidad étnica
    dbc.Row([
        dbc.Col(dcc.Graph(id='chart-sexo',  config={'displayModeBar': False}), md=3),
        dbc.Col(dcc.Graph(id='chart-edad',  config={'displayModeBar': False}), md=3),
        dbc.Col(dcc.Graph(id='chart-lgbti', config={'displayModeBar': False}), md=3),
        dbc.Col(dcc.Graph(id='chart-etnia', config={'displayModeBar': False}), md=3),
    ], className='mb-3 g-2'),

    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN: TASA DE ESCNNA
    # ══════════════════════════════════════════════════════════════════════════
    html.Div(id='section-tasa-title'),

    html.Div(id='info-tasa', className='mb-3'),

    # Mapa tasa departamentos + tabla
    dbc.Card(dbc.CardBody(
        dbc.Row([
            dbc.Col(dcc.Graph(id='map-dep-tasa', config={'displayModeBar': False}), md=8),
            dbc.Col([
                html.P(id='lbl-tasa-dep', style={**FILTER_LABEL, 'marginBottom': '8px'}),
                html.Div(id='table-dep-tasa'),
            ], md=4, style={'paddingTop': '12px'}),
        ], className='g-2')
    ), className='shadow-sm border-0 mb-3'),

    # Mapa tasa municipios + top 20
    dbc.Card(dbc.CardBody(
        dbc.Row([
            dbc.Col(dcc.Graph(id='map-mun-tasa', config={'displayModeBar': False}), md=8),
            dbc.Col([
                html.P(id='lbl-tasa-mun', style={**FILTER_LABEL, 'marginBottom': '8px'}),
                html.Div(id='table-mun-tasa'),
            ], md=4, style={'paddingTop': '12px'}),
        ], className='g-2')
    ), className='shadow-sm border-0 mb-3'),

    # Histórico de tasa
    dbc.Card(dbc.CardBody(
        dcc.Graph(id='chart-hist-tasa', config={'displayModeBar': False})
    ), className='shadow-sm border-0 mb-3'),

    # ══════════════════════════════════════════════════════════════════════════
    # SECCIÓN: JUSTICIA Y DELITOS
    # ══════════════════════════════════════════════════════════════════════════
    section_title('Justicia y Delitos'),

    dbc.Row([
        dbc.Col(dcc.Graph(id='chart-delito', config={'displayModeBar': False}), md=8),
        dbc.Col(dcc.Graph(id='chart-estado', config={'displayModeBar': False}), md=4),
    ], className='mb-3 g-2'),
])


# ── Callback ──────────────────────────────────────────────────────────────────
@callback(
    [Output('kpi-casos',       'children'),
     Output('kpi-victimas',    'children'),
     Output('map-dep-count',   'figure'),
     Output('table-dep-count', 'children'),
     Output('map-mun-count',   'figure'),
     Output('table-mun-count', 'children'),
     Output('chart-historico', 'figure'),
     Output('chart-sexo',      'figure'),
     Output('chart-edad',      'figure'),
     Output('chart-lgbti',     'figure'),
     Output('chart-etnia',     'figure'),
     Output('map-dep-tasa',    'figure'),
     Output('table-dep-tasa',  'children'),
     Output('map-mun-tasa',    'figure'),
     Output('table-mun-tasa',  'children'),
     Output('chart-hist-tasa', 'figure'),
     Output('chart-delito',    'figure'),
     Output('chart-estado',    'figure'),
     Output('section-tasa-title', 'children'),
     Output('info-tasa',          'children'),
     Output('lbl-tasa-dep',       'children'),
     Output('lbl-tasa-mun',       'children')],
    [Input('f-anio',   'value'),
     Input('f-grupo',  'value'),
     Input('f-depto',  'value'),
     Input('f-delito', 'value')],
)
def update_all(anios, grupos, depto, delitos):
    dff      = filter_df(anios, grupos, depto, delitos)
    dff_full = filter_df_no_year(grupos, depto, delitos)

    empty_t = html.P('Sin datos', style={'color': C_GRAY, 'fontSize': '0.8rem'})

    # ── Etiqueta dinámica según grupo seleccionado ────────────────────────────
    if grupos == 'Trata de Personas':
        tasa_nombre = 'Trata con NNA'
    else:
        tasa_nombre = 'ESCNNA'

    _INTRO = ('Es evidente que los territorios con mayor número de habitantes pueden '
              'presentar mayor número de víctimas y casos. Por lo tanto, es necesario '
              'controlar por el tamaño poblacional para tener un panorama más claro del '
              'delito. Esto se resuelve construyendo una tasa que tenga en cuenta esta situación.')
    _DEFS = {
        'ESCNNA':        [html.Strong('La Tasa de ESCNNA: '), 'Se define como el ',
                          html.Strong('número de víctimas de ESCNNA por cada 100.000 habitantes menores de edad')],
        'Trata con NNA': [html.Strong('La Tasa de Trata con NNA: '), 'Se define como el ',
                          html.Strong('número de víctimas de Trata con NNA por cada 100.000 habitantes menores de edad')],
    }
    info_tasa = html.Div([html.P(_INTRO, className='mb-3'),
                          html.P(_DEFS[tasa_nombre], className='mb-0')], style=INFO_STYLE)
    section_tasa = section_title(f'Tasa de {tasa_nombre}')

    if dff.empty and dff_full.empty:
        empty = empty_fig()
        return ([kpi_card('Sin datos', 0)] * 2 +
                [empty_fig(height=780), empty_t] * 2 +
                [empty] * 5 +
                [empty_fig(height=780), empty_t] * 2 +
                [empty] * 3 +
                [section_tasa, info_tasa,
                 f'Tasa de {tasa_nombre} por departamento',
                 f'Top 20 municipios por tasa de {tasa_nombre.lower()}'])

    # ── Años para join con población ──────────────────────────────────────────
    years_sel = list(range(int(anios[0]), int(anios[1]) + 1)) if anios else YEARS

    # ── GeoJSON municipios filtrado ───────────────────────────────────────────
    if depto and depto != 'Todos':
        geo_mun_sel = {
            'type': 'FeatureCollection',
            'features': [f for f in geojson_mun['features']
                         if f['properties']['departamento'] == depto]
        }
    else:
        geo_mun_sel = geojson_mun

    # ── KPIs ─────────────────────────────────────────────────────────────────
    total_casos    = len(dff)
    total_victimas = int(dff['total_victimas'].sum())
    kpi_casos    = kpi_card('Casos registrados', total_casos,    C_PRIMARY, 'en el período seleccionado')
    kpi_victimas = kpi_card('Total víctimas',    total_victimas, C_DARK,    'en el período seleccionado')

    # ── Conteo de víctimas ────────────────────────────────────────────────────
    dep_cnt = (dff.groupby(['cod_dep', 'departamento_hecho'], as_index=False)
                  ['total_victimas_nna'].sum()
                  .rename(columns={'total_victimas_nna': 'victimas'}))
    mun_cnt = (dff.dropna(subset=['cod_mun'])
                  .groupby(['cod_mun', 'municipio_hecho'], as_index=False)
                  ['total_victimas_nna'].sum()
                  .rename(columns={'total_victimas_nna': 'victimas'}))

    # ── Choropleth helper ─────────────────────────────────────────────────────
    def choropleth(data, geojson, loc_col, feat_key, colorscale, label,
                   name_col, val_fmt=':.0f', height=780, title='', bounds=None):
        if not geojson.get('features'):
            return empty_fig(height=height)

        prop_key = feat_key.split('.')[-1]
        all_codes = [f['properties'][prop_key]          for f in geojson['features']]
        all_names = [f['properties'].get('nombre', '') for f in geojson['features']]

        fig = go.Figure()

        # Capa base: todos los polígonos en gris — aparecen aunque no tengan datos
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            locations=all_codes,
            z=[0] * len(all_codes),
            featureidkey=feat_key,
            colorscale=[[0, '#dde3ea'], [1, '#dde3ea']],
            showscale=False,
            showlegend=False,
            customdata=all_names,
            hovertemplate='<b>%{customdata}</b><br>Sin datos<extra></extra>',
            marker_line_color='#9ab0be',
            marker_line_width=0.6,
            name='',
        ))

        # Capa de datos: coloraxis dedicado para no contaminar la escala base
        if not data.empty:
            z_vals = data['victimas']
            fig.add_trace(go.Choropleth(
                geojson=geojson,
                locations=data[loc_col],
                featureidkey=feat_key,
                coloraxis='coloraxis2',
                z=z_vals,
                showlegend=False,
                customdata=data[[name_col]].values,
                hovertemplate=(
                    f'<b>%{{customdata[0]}}</b><br>'
                    f'{label}: %{{z{val_fmt}}}<extra></extra>'
                ),
                marker_line_color='#9ab0be',
                marker_line_width=0.6,
                name='',
            ))
            fig.update_layout(coloraxis2=dict(
                colorscale=colorscale,
                cmin=z_vals.min(),
                cmax=z_vals.max(),
                showscale=False,
            ))

        geo_cfg = dict(visible=False, bgcolor='rgba(0,0,0,0)')
        if bounds:
            geo_cfg['lataxis'] = dict(range=bounds['lat'])
            geo_cfg['lonaxis'] = dict(range=bounds['lon'])
        else:
            geo_cfg['fitbounds'] = 'locations'
        fig.update_geos(**geo_cfg)
        t_margin = 48 if title else 10
        apply_layout(fig, height=height, title=title,
                     margin=dict(l=0, r=10, t=t_margin, b=0),
                     showlegend=False)
        fig.update_layout(geo=dict(domain=dict(x=[0, 1], y=[0, 1])))
        return fig

    mun_bounds = _DEP_MUN_BOUNDS.get(depto) if depto and depto != 'Todos' else _MUN_BOUNDS

    fig_dep_count = choropleth(dep_cnt, geojson_dep, 'cod_dep', 'properties.cod_dep',
                                COLORSCALE_COUNT, 'Víctimas', 'departamento_hecho', ':,',
                                title='Víctimas NNA por departamento', bounds=_DEP_BOUNDS)
    fig_mun_count = choropleth(mun_cnt, geo_mun_sel, 'cod_mun', 'properties.cod_mun',
                                COLORSCALE_COUNT, 'Víctimas', 'municipio_hecho', ':,',
                                title='Víctimas NNA por municipio', bounds=mun_bounds)

    dep_rows = [(r['departamento_hecho'], f"{r['victimas']:,}")
                for _, r in dep_cnt.sort_values('victimas', ascending=False).iterrows()]
    mun_rows = [(r['municipio_hecho'], f"{r['victimas']:,}")
                for _, r in mun_cnt.sort_values('victimas', ascending=False).head(20).iterrows()]

    tbl_dep_count = rank_table(dep_rows, 'Departamento', 'Víctimas', max_height='742px')
    tbl_mun_count = rank_table(mun_rows, 'Municipio',    'Víctimas', max_height='742px')

    # ── Tasas ─────────────────────────────────────────────────────────────────
    pop_dep = (df_dep_pop[df_dep_pop['AÑO'].isin(years_sel)]
               .groupby('cod_dep', as_index=False)['Total'].sum())
    pop_mun = (df_mun_pop[df_mun_pop['AÑO'].isin(years_sel)]
               .groupby('cod_mun', as_index=False)['Total'].sum())

    dep_tasa = dep_cnt.merge(pop_dep, on='cod_dep', how='left')
    dep_tasa['victimas'] = (dep_tasa['victimas'] / dep_tasa['Total'] * 100_000).round(2)
    dep_tasa = dep_tasa.dropna(subset=['victimas'])

    mun_tasa = mun_cnt.merge(pop_mun, on='cod_mun', how='left')
    mun_tasa['victimas'] = (mun_tasa['victimas'] / mun_tasa['Total'] * 100_000).round(2)
    mun_tasa = mun_tasa.dropna(subset=['victimas'])

    fig_dep_tasa = choropleth(dep_tasa, geojson_dep, 'cod_dep', 'properties.cod_dep',
                               COLORSCALE_RATE, f'Tasa de {tasa_nombre}', 'departamento_hecho', ':.2f',
                               title=f'Tasa de {tasa_nombre} por departamento', bounds=_DEP_BOUNDS)
    fig_mun_tasa = choropleth(mun_tasa, geo_mun_sel, 'cod_mun', 'properties.cod_mun',
                               COLORSCALE_RATE, f'Tasa de {tasa_nombre}', 'municipio_hecho', ':.2f',
                               title=f'Tasa de {tasa_nombre} por municipio', bounds=mun_bounds)

    dep_tasa_rows = [(r['departamento_hecho'], f"{r['victimas']:.2f}")
                     for _, r in dep_tasa.sort_values('victimas', ascending=False).iterrows()]
    mun_tasa_rows = [(r['municipio_hecho'], f"{r['victimas']:.2f}")
                     for _, r in mun_tasa.sort_values('victimas', ascending=False).head(20).iterrows()]

    tbl_dep_tasa = rank_table(dep_tasa_rows, 'Departamento', f'Tasa de {tasa_nombre}', max_height='742px')
    tbl_mun_tasa = rank_table(mun_tasa_rows, 'Municipio',    f'Tasa de {tasa_nombre}', max_height='742px')

    # ── Histórico (sin filtro de año) ─────────────────────────────────────────
    hist = (dff_full.dropna(subset=['anio_denuncia'])
                    .assign(anio=lambda x: x['anio_denuncia'].astype(int))
                    .groupby('anio', as_index=False)
                    .agg(casos=('total_victimas', 'count'),
                         victimas=('total_victimas', 'sum'))
                    .sort_values('anio'))

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(
        x=hist['anio'], y=hist['victimas'],
        name='Víctimas', marker_color=C_PRIMARY, opacity=0.85,
        text=hist['victimas'], texttemplate='%{text:,}',
        textposition='outside', textfont=dict(size=13),
    ))
    fig_hist.add_trace(go.Scatter(
        x=hist['anio'], y=hist['casos'],
        name='Casos', mode='lines+markers+text',
        line=dict(color=C_CYAN, width=3), marker=dict(size=9),
        text=hist['casos'], texttemplate='%{text:,}',
        textposition='top center', textfont=dict(size=12, color=C_CYAN),
    ))
    apply_layout(fig_hist, height=408,
                 title='Histórico de casos y víctimas', legend_bottom=True,
                 yaxis=dict(title='', showgrid=True, gridcolor='#eeeeee',
                            tickfont=dict(size=12)),
                 xaxis=dict(tickmode='linear', dtick=1, tickfont=dict(size=12)),
                 barmode='group')

    # ── Sexo ──────────────────────────────────────────────────────────────────
    sexo = (dff[dff['sexo'] != 'SIN DATO']
               .groupby('sexo', as_index=False)['total_victimas'].sum())
    if sexo.empty:
        fig_sexo = empty_fig('Sin datos')
    else:
        fig_sexo = go.Figure(go.Pie(
            labels=sexo['sexo'], values=sexo['total_victimas'],
            hole=0.45,
            marker=dict(colors=[C_PRIMARY, C_CYAN, C_PURPLE_LT]),
            textinfo='percent+label', textposition='inside',
        ))
        apply_layout(fig_sexo, height=310, title='Víctimas por sexo')

    # ── Edad ──────────────────────────────────────────────────────────────────
    edad_order = ['NIÑA-NIÑO (0-13 años)', 'ADOLESCENTE (14-17 años)', 'ADULTO', 'SIN DATO']
    edad = dff.groupby('grupo_etario', as_index=False)['total_victimas'].sum()
    edad['grupo_etario'] = pd.Categorical(edad['grupo_etario'], categories=edad_order, ordered=True)
    edad = edad.sort_values('grupo_etario')

    total_edad = edad['total_victimas'].sum()
    edad['pct'] = (edad['total_victimas'] / total_edad * 100).round(1)

    fig_edad = go.Figure(go.Bar(
        x=edad['total_victimas'], y=edad['grupo_etario'],
        orientation='h',
        marker=dict(color=[C_DARK, C_PRIMARY, C_CYAN, C_GRAY]),
        text=edad['total_victimas'], textposition='outside',
        customdata=edad[['pct']].values,
        hovertemplate='%{y}<br>Víctimas: %{x:,}<br>Porcentaje: %{customdata[0]:.1f}%<extra></extra>',
    ))
    apply_layout(fig_edad, height=310, title='Víctimas por grupo etario',
                 xaxis=dict(showgrid=True, gridcolor='#eeeeee'),
                 yaxis=dict(title=''),
                 showlegend=False)

    # ── Diversidad sexual ─────────────────────────────────────────────────────
    lgbti_si = int(dff[dff['aplica_lgbti'] == 'SI']['total_victimas'].sum())
    lgbti_no = int(dff[dff['aplica_lgbti'] == 'NO']['total_victimas'].sum())
    fig_lgbti = go.Figure(go.Pie(
        labels=['LGBTIQ+', 'No identificado'],
        values=[lgbti_si, lgbti_no],
        hole=0.45,
        marker=dict(colors=[C_PURPLE, C_LAVENDER]),
        textinfo='percent+label', textposition='inside',
    ))
    apply_layout(fig_lgbti, height=310, title='Diversidad sexual')

    # ── Diversidad étnica ─────────────────────────────────────────────────────
    etnia_labels = ['Ninguna', 'Indígena', 'Afrodescendiente']
    etnia_values = [
        int(dff[(dff['indigena'] == 'NO') & (dff['afrodescendiente'] == 'NO')]['total_victimas'].sum()),
        int(dff[dff['indigena'] == 'SI']['total_victimas'].sum()),
        int(dff[dff['afrodescendiente'] == 'SI']['total_victimas'].sum()),
    ]
    fig_etnia = go.Figure(go.Pie(
        labels=etnia_labels, values=etnia_values,
        hole=0.45,
        marker=dict(colors=[C_GRAY, C_TEAL, C_ORANGE]),
        textinfo='percent+label', textposition='inside',
    ))
    apply_layout(fig_etnia, height=310, title='Diversidad étnica')

    # ── Histórico de tasa (sin filtro de año) ─────────────────────────────────
    hist_nna = (dff_full.dropna(subset=['anio_denuncia'])
                        .assign(anio=lambda x: x['anio_denuncia'].astype(int))
                        .groupby('anio', as_index=False)['total_victimas_nna'].sum())
    hist_nna = hist_nna.merge(POP_NATIONAL, left_on='anio', right_on='AÑO', how='left')
    hist_nna['tasa'] = (hist_nna['total_victimas_nna'] / hist_nna['Total'] * 100_000).round(2)
    hist_nna = hist_nna.dropna(subset=['tasa']).sort_values('anio')

    if hist_nna.empty:
        fig_hist_tasa = empty_fig('Sin datos de tasa')
    else:
        fig_hist_tasa = go.Figure(go.Scatter(
            x=hist_nna['anio'], y=hist_nna['tasa'],
            mode='lines+markers+text',
            line=dict(color=C_ORANGE, width=2.5), marker=dict(size=7),
            fill='tozeroy', fillcolor='rgba(243,156,18,0.12)',
            text=hist_nna['tasa'], texttemplate='%{text:.2f}',
            textposition='top center', textfont=dict(size=13),
            name='Tasa de ESCNNA',
        ))
        apply_layout(fig_hist_tasa, height=384,
                     title=f'Histórico de tasa de {tasa_nombre} por año (×100.000 menores)',
                     xaxis=dict(title='Año', tickmode='linear', dtick=1),
                     yaxis=dict(title=f'Tasa de {tasa_nombre}', showgrid=True, gridcolor='#eeeeee'),
                     showlegend=False)

    # ── Por delito ────────────────────────────────────────────────────────────
    delito_df = (dff.groupby('delito', as_index=False)['total_victimas_nna'].sum()
                    .sort_values('total_victimas_nna', ascending=True).tail(15))
    total_delito = delito_df['total_victimas_nna'].sum()
    delito_df['pct'] = (delito_df['total_victimas_nna'] / total_delito * 100).round(1)

    fig_delito = go.Figure(go.Bar(
        x=delito_df['total_victimas_nna'], y=delito_df['delito'],
        orientation='h',
        marker=dict(color=delito_df['total_victimas_nna'],
                    colorscale=COLORSCALE_COUNT, showscale=False),
        text=delito_df['total_victimas_nna'], textposition='outside',
        customdata=delito_df[['pct']].values,
        hovertemplate='%{y}<br>Víctimas NNA: %{x:,}<br>Porcentaje: %{customdata[0]:.1f}%<extra></extra>',
    ))
    apply_layout(fig_delito, height=460, title='Top 15 delitos por víctimas NNA',
                 xaxis=dict(title='Víctimas NNA', showgrid=True, gridcolor='#eeeeee'),
                 yaxis=dict(title='', tickfont=dict(size=10)),
                 showlegend=False)

    # ── Etapa de casos por año ─────────────────────────────────────────────────
    etapa = (dff.dropna(subset=['anio_denuncia', 'etapa_caso'])
                .assign(anio=lambda x: x['anio_denuncia'].astype(int))
                .groupby(['anio', 'etapa_caso'], as_index=False)['total_victimas'].sum()
                .sort_values('anio'))

    color_list = [C_GRAY, C_CYAN, C_PRIMARY, C_GREEN, C_DARK, C_ORANGE, C_PURPLE]
    fig_estado = go.Figure()
    for i, etap in enumerate(sorted(etapa['etapa_caso'].unique())):
        color = ETAPA_COLORS.get(etap, color_list[i % len(color_list)])
        sub = etapa[etapa['etapa_caso'] == etap]
        fig_estado.add_trace(go.Bar(
            x=sub['anio'], y=sub['total_victimas'],
            name=etap.title(), marker_color=color,
        ))
    apply_layout(fig_estado, height=460, title='Etapa de casos por año',
                 legend_bottom=True,
                 barmode='stack',
                 xaxis=dict(title='Año', tickmode='linear', dtick=1),
                 yaxis=dict(title='Víctimas', showgrid=True, gridcolor='#eeeeee'))

    return (kpi_casos, kpi_victimas,
            fig_dep_count, tbl_dep_count,
            fig_mun_count, tbl_mun_count,
            fig_hist,
            fig_sexo, fig_edad, fig_lgbti, fig_etnia,
            fig_dep_tasa, tbl_dep_tasa,
            fig_mun_tasa, tbl_mun_tasa,
            fig_hist_tasa,
            fig_delito, fig_estado,
            section_tasa, info_tasa,
            f'Tasa de {tasa_nombre} por departamento',
            f'Top 20 municipios por tasa de {tasa_nombre.lower()}')


if __name__ == '__main__':
    app.run(debug=True, port=8050)

import os
import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc

# ── Rutas ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

COLORSCALE_COUNT = [[0, '#e8f1fd'], [0.5, C_PRIMARY],  [1, C_DARKEST]]
COLORSCALE_RATE  = [[0, '#fef9e7'], [0.5, C_ORANGE],   [1, C_RED]]

FILTER_LABEL = {'fontSize': '0.75rem', 'fontWeight': 600,
                'color': C_DARKEST, 'marginBottom': '4px'}

# ── Datos ──────────────────────────────────────────────────────────────────────
df = pd.read_csv(os.path.join(DATA_DIR, 'victimas.csv'),
                 encoding='utf-8-sig', dtype={'cod_dep': str, 'cod_mun': str})
df_dep_pop = pd.read_csv(os.path.join(DATA_DIR, 'poblacion_depto.csv'),
                         encoding='utf-8-sig', dtype={'cod_dep': str})
df_mun_pop = pd.read_csv(os.path.join(DATA_DIR, 'poblacion_mpio.csv'),
                         encoding='utf-8-sig', dtype={'cod_dep': str, 'cod_mun': str})

df['anio_denuncia']     = pd.to_numeric(df['anio_denuncia'],     errors='coerce')
df['total_victimas']    = pd.to_numeric(df['total_victimas'],    errors='coerce').fillna(0).astype(int)
df['total_victimas_nna']= pd.to_numeric(df['total_victimas_nna'],errors='coerce').fillna(0).astype(int)

with open(os.path.join(ASSETS_DIR, 'geojson', 'departamentos.geojson'), encoding='utf-8') as f:
    geojson_dep = json.load(f)
with open(os.path.join(ASSETS_DIR, 'geojson', 'municipios.geojson'), encoding='utf-8') as f:
    geojson_mun = json.load(f)

YEARS     = sorted(df['anio_denuncia'].dropna().astype(int).unique().tolist())
YEAR_MIN, YEAR_MAX = YEARS[0], YEARS[-1]
GRUPOS    = sorted(df['grupo_delito'].dropna().unique().tolist())
DEPTOS    = sorted(df['departamento_hecho'].dropna().unique().tolist())
DELITOS   = sorted(df['delito'].dropna().unique().tolist())

# ── Helpers ────────────────────────────────────────────────────────────────────
def filter_df(anios, grupos, depto, delitos):
    mask = pd.Series(True, index=df.index)
    if anios:
        mask &= df['anio_denuncia'].between(anios[0], anios[1])
    if grupos:
        mask &= df['grupo_delito'].isin(grupos)
    if depto and depto != 'Todos':
        mask &= df['departamento_hecho'] == depto
    if delitos:
        mask &= df['delito'].isin(delitos)
    return df[mask].copy()


def apply_layout(fig, height=320, title='', legend_h=False, **extra):
    """Aplica el layout base directamente sobre la figura, sin desempaquetar dicts."""
    args = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Inter, Arial, sans-serif', color=C_DARKEST),
        margin=dict(l=10, r=10, t=45, b=10),
        height=height,
        legend=dict(orientation='h', y=1.12, bgcolor='rgba(0,0,0,0)')
               if legend_h else dict(bgcolor='rgba(0,0,0,0)'),
    )
    if title:
        args['title'] = dict(text=title, font=dict(size=13), x=0, pad=dict(l=4))
    args.update(extra)
    fig.update_layout(**args)


def empty_fig(msg='Sin datos', height=320):
    fig = go.Figure()
    fig.add_annotation(text=msg, xref='paper', yref='paper',
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=13, color=C_GRAY))
    apply_layout(fig, height)
    return fig


def kpi_card(title, value, color=C_PRIMARY):
    return dbc.Card([
        dbc.CardBody([
            html.P(title, className='text-muted mb-1', style={'fontSize': '0.78rem'}),
            html.H4(f'{value:,}', style={'color': color, 'fontWeight': 700, 'margin': 0}),
        ])
    ], className='shadow-sm border-0 h-100')


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

    # Header
    dbc.Row(dbc.Col(html.Div([
        html.H4('Observatorio ESCNNA',
                style={'color': C_WHITE, 'fontWeight': 700, 'margin': 0}),
        html.P('Explotación Sexual Comercial y Trata de Personas con NNA · Colombia',
               style={'color': C_LAVENDER, 'margin': 0, 'fontSize': '0.82rem'}),
    ], style={'backgroundColor': C_DARKEST, 'padding': '14px 24px'})),
    className='mb-3'),

    # Filtros
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
                multi=True, placeholder='Todos', style={'fontSize': '0.83rem'}),
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
    ])), className='shadow-sm border-0 mb-3'),

    # KPIs
    dbc.Row([
        dbc.Col(id='kpi-casos',    md=4, className='mb-2'),
        dbc.Col(id='kpi-victimas', md=4, className='mb-2'),
        dbc.Col(id='kpi-nna',      md=4, className='mb-2'),
    ], className='mb-3 g-2'),

    # Mapas 2x2
    dbc.Card(dbc.CardBody([
        html.P('Mapas', style={**FILTER_LABEL, 'fontSize': '0.85rem', 'marginBottom': '8px'}),
        dbc.Row([
            dbc.Col([
                html.P('Víctimas por departamento', style=FILTER_LABEL),
                dcc.Graph(id='map-dep-count', config={'displayModeBar': False}),
            ], md=3),
            dbc.Col([
                html.P('Tasa ESCNNA por departamento (×100k menores)', style=FILTER_LABEL),
                dcc.Graph(id='map-dep-tasa', config={'displayModeBar': False}),
            ], md=3),
            dbc.Col([
                html.P('Víctimas por municipio', style=FILTER_LABEL),
                dcc.Graph(id='map-mun-count', config={'displayModeBar': False}),
            ], md=3),
            dbc.Col([
                html.P('Tasa ESCNNA por municipio (×100k menores)', style=FILTER_LABEL),
                dcc.Graph(id='map-mun-tasa', config={'displayModeBar': False}),
            ], md=3),
        ], className='g-2'),
    ]), className='shadow-sm border-0 mb-3'),

    # Gráficas fila 1
    dbc.Row([
        dbc.Col(dcc.Graph(id='chart-historico', config={'displayModeBar': False}), md=8),
        dbc.Col(dcc.Graph(id='chart-sexo',      config={'displayModeBar': False}), md=4),
    ], className='mb-3 g-2'),

    # Gráficas fila 2
    dbc.Row([
        dbc.Col(dcc.Graph(id='chart-edad',   config={'displayModeBar': False}), md=4),
        dbc.Col(dcc.Graph(id='chart-etnia',  config={'displayModeBar': False}), md=4),
        dbc.Col(dcc.Graph(id='chart-estado', config={'displayModeBar': False}), md=4),
    ], className='mb-3 g-2'),

    # Distribución por delito
    dbc.Row(
        dbc.Col(dcc.Graph(id='chart-delito', config={'displayModeBar': False})),
    className='mb-2'),
])


# ── Callback ──────────────────────────────────────────────────────────────────
@callback(
    [Output('kpi-casos',       'children'),
     Output('kpi-victimas',    'children'),
     Output('kpi-nna',         'children'),
     Output('map-dep-count',   'figure'),
     Output('map-dep-tasa',    'figure'),
     Output('map-mun-count',   'figure'),
     Output('map-mun-tasa',    'figure'),
     Output('chart-historico', 'figure'),
     Output('chart-sexo',      'figure'),
     Output('chart-edad',      'figure'),
     Output('chart-etnia',     'figure'),
     Output('chart-estado',    'figure'),
     Output('chart-delito',    'figure')],
    [Input('f-anio',   'value'),
     Input('f-grupo',  'value'),
     Input('f-depto',  'value'),
     Input('f-delito', 'value')],
)
def update_all(anios, grupos, depto, delitos):
    dff = filter_df(anios, grupos, depto, delitos)

    if dff.empty:
        empty = empty_fig()
        empty_kpi = kpi_card('Sin datos', 0)
        return ([empty_kpi] * 3 + [empty_fig(height=350)] * 4 + [empty] * 6)

    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpis = (
        kpi_card('Casos registrados', len(dff),                           C_PRIMARY),
        kpi_card('Total víctimas',    int(dff['total_victimas'].sum()),    C_DARK),
        kpi_card('Víctimas NNA',      int(dff['total_victimas_nna'].sum()), C_PURPLE),
    )

    # ── Años seleccionados para join con población ────────────────────────────
    years_sel = list(range(int(anios[0]), int(anios[1]) + 1)) if anios else YEARS

    # ── GeoJSON de municipios (filtrado si hay departamento seleccionado) ─────
    if depto and depto != 'Todos':
        geo_mun_sel = {
            'type': 'FeatureCollection',
            'features': [f for f in geojson_mun['features']
                         if f['properties']['departamento'] == depto]
        }
    else:
        geo_mun_sel = geojson_mun

    # ── Mapas: conteo ─────────────────────────────────────────────────────────
    dep_cnt = (dff.groupby('cod_dep', as_index=False)['total_victimas_nna']
                  .sum().rename(columns={'total_victimas_nna': 'victimas'}))
    mun_cnt = (dff.dropna(subset=['cod_mun'])
                  .groupby('cod_mun', as_index=False)['total_victimas_nna']
                  .sum().rename(columns={'total_victimas_nna': 'victimas'}))

    def choropleth(data, geojson, loc_col, feat_key, colorscale, label):
        if data.empty:
            return empty_fig(height=350)
        fig = px.choropleth(
            data, geojson=geojson, locations=loc_col,
            featureidkey=feat_key, color='victimas',
            color_continuous_scale=colorscale,
            labels={'victimas': label},
            hover_data={loc_col: False, 'victimas': True},
        )
        fig.update_geos(fitbounds='locations', visible=False)
        apply_layout(fig, height=350,
                     coloraxis_colorbar=dict(thickness=10, len=0.65, title=''))
        return fig

    fig_dep_count = choropleth(dep_cnt, geojson_dep,  'cod_dep', 'properties.cod_dep',
                                COLORSCALE_COUNT, 'Víctimas')
    fig_mun_count = choropleth(mun_cnt, geo_mun_sel,  'cod_mun', 'properties.cod_mun',
                                COLORSCALE_COUNT, 'Víctimas')

    # ── Mapas: tasa ───────────────────────────────────────────────────────────
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
                               COLORSCALE_RATE, 'Tasa ×100k')
    fig_mun_tasa = choropleth(mun_tasa, geo_mun_sel, 'cod_mun', 'properties.cod_mun',
                               COLORSCALE_RATE, 'Tasa ×100k')

    # ── Histórico ─────────────────────────────────────────────────────────────
    hist = (dff.dropna(subset=['anio_denuncia'])
               .assign(anio=lambda x: x['anio_denuncia'].astype(int))
               .groupby('anio', as_index=False)
               .agg(casos=('total_victimas', 'count'),
                    victimas=('total_victimas', 'sum'))
               .sort_values('anio'))

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(
        x=hist['anio'], y=hist['victimas'],
        name='Víctimas', marker_color=C_PRIMARY, opacity=0.85,
        yaxis='y1',
    ))
    fig_hist.add_trace(go.Scatter(
        x=hist['anio'], y=hist['casos'],
        name='Casos', mode='lines+markers',
        line=dict(color=C_CYAN, width=2.5), marker=dict(size=6),
        yaxis='y2',
    ))
    apply_layout(fig_hist, height=320,
                 title='Histórico de casos y víctimas', legend_h=True,
                 yaxis=dict(title='Víctimas', showgrid=True, gridcolor='#eeeeee'),
                 yaxis2=dict(title='Casos', overlaying='y', side='right', showgrid=False),
                 xaxis=dict(tickmode='linear', dtick=1),
                 barmode='group')

    # ── Sexo ──────────────────────────────────────────────────────────────────
    sexo = (dff[dff['sexo'] != 'SIN DATO']
               .groupby('sexo', as_index=False)['total_victimas'].sum())
    if sexo.empty:
        fig_sexo = empty_fig('Sin datos de sexo')
    else:
        fig_sexo = go.Figure(go.Pie(
            labels=sexo['sexo'], values=sexo['total_victimas'],
            hole=0.45,
            marker=dict(colors=[C_PRIMARY, C_CYAN, C_PURPLE_LT]),
            textinfo='percent+label', textposition='inside',
        ))
        apply_layout(fig_sexo, height=320, title='Víctimas por sexo')

    # ── Edad ──────────────────────────────────────────────────────────────────
    edad_order = ['NIÑA-NIÑO (0-13 años)', 'ADOLESCENTE (14-17 años)', 'ADULTO', 'SIN DATO']
    edad = dff.groupby('grupo_etario', as_index=False)['total_victimas'].sum()
    edad['grupo_etario'] = pd.Categorical(edad['grupo_etario'], categories=edad_order, ordered=True)
    edad = edad.sort_values('grupo_etario')

    fig_edad = go.Figure(go.Bar(
        x=edad['total_victimas'], y=edad['grupo_etario'],
        orientation='h',
        marker=dict(color=[C_DARK, C_PRIMARY, C_CYAN, C_GRAY]),
        text=edad['total_victimas'], textposition='outside',
    ))
    apply_layout(fig_edad, height=320, title='Víctimas por grupo etario',
                 xaxis=dict(title='Víctimas'), yaxis=dict(title=''),
                 showlegend=False)

    # ── Etnia / LGBTIQ+ ───────────────────────────────────────────────────────
    etnia_rows = [
        ('Ninguna',         int(dff[(dff['aplica_lgbti']=='NO') & (dff['indigena']=='NO') & (dff['afrodescendiente']=='NO')]['total_victimas'].sum())),
        ('LGBTIQ+',         int(dff[dff['aplica_lgbti']=='SI']['total_victimas'].sum())),
        ('Indígena',        int(dff[dff['indigena']=='SI']['total_victimas'].sum())),
        ('Afrodescendiente',int(dff[dff['afrodescendiente']=='SI']['total_victimas'].sum())),
    ]
    etnia_df = pd.DataFrame(etnia_rows, columns=['categoria', 'victimas'])

    fig_etnia = go.Figure(go.Bar(
        x=etnia_df['victimas'], y=etnia_df['categoria'],
        orientation='h',
        marker=dict(color=[C_GRAY, C_PURPLE, C_TEAL, C_ORANGE]),
        text=etnia_df['victimas'], textposition='outside',
    ))
    apply_layout(fig_etnia, height=320, title='Víctimas por identidad / etnia',
                 xaxis=dict(title='Víctimas'), yaxis=dict(title=''),
                 showlegend=False)

    # ── Estado por año ────────────────────────────────────────────────────────
    estado = (dff.dropna(subset=['anio_denuncia'])
                 .assign(anio=lambda x: x['anio_denuncia'].astype(int))
                 .groupby(['anio', 'estado'], as_index=False)['total_victimas'].sum()
                 .sort_values('anio'))

    fig_estado = go.Figure()
    for est, color in [('ACTIVO', C_PRIMARY), ('INACTIVO', C_GRAY)]:
        sub = estado[estado['estado'] == est]
        fig_estado.add_trace(go.Bar(
            x=sub['anio'], y=sub['total_victimas'],
            name=est, marker_color=color,
        ))
    apply_layout(fig_estado, height=320, title='Estado de casos por año', legend_h=True,
                 barmode='stack',
                 xaxis=dict(title='Año', tickmode='linear', dtick=1),
                 yaxis=dict(title='Víctimas', showgrid=True, gridcolor='#eeeeee'))

    # ── Por delito ────────────────────────────────────────────────────────────
    delito_df = (dff.groupby('delito', as_index=False)['total_victimas_nna'].sum()
                    .sort_values('total_victimas_nna', ascending=True)
                    .tail(15))

    fig_delito = go.Figure(go.Bar(
        x=delito_df['total_victimas_nna'], y=delito_df['delito'],
        orientation='h',
        marker=dict(
            color=delito_df['total_victimas_nna'],
            colorscale=COLORSCALE_COUNT,
            showscale=False,
        ),
        text=delito_df['total_victimas_nna'], textposition='outside',
    ))
    apply_layout(fig_delito, height=440, title='Top 15 delitos por víctimas NNA',
                 xaxis=dict(title='Víctimas NNA'),
                 yaxis=dict(title='', tickfont=dict(size=10)),
                 showlegend=False)

    return (*kpis,
            fig_dep_count, fig_dep_tasa, fig_mun_count, fig_mun_tasa,
            fig_hist, fig_sexo, fig_edad, fig_etnia, fig_estado, fig_delito)


if __name__ == '__main__':
    app.run(debug=True, port=8050)

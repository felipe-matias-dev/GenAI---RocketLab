"""Gera tests/fixtures/cinerocket_sample.db: uma amostra pequena do cinerocket.db.

O banco real (~580MB) não vai para o GitHub, mas 61 testes dependem do schema
e de alguns valores dele (ex.: o gênero "Science Fiction", nomes duplicados em
dim_people). A amostra tem o MESMO schema (DDL copiado do original, com
índices) e um recorte coerente dos dados — os filmes mais populares com
receita e orçamento informados, mais filmes pouco populares sem receita
(elenco pequeno, arquivo leve), e todas as linhas que se ligam a eles —,
para o CI rodar a suíte inteira sem o banco real (~4MB):

    DB_PATH=tests/fixtures/cinerocket_sample.db pytest

Uso (precisa do banco real em data/cinerocket.db):
    python -m scripts.build_sample_db
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE = BASE_DIR / "data" / "cinerocket.db"
TARGET = BASE_DIR / "tests" / "fixtures" / "cinerocket_sample.db"

# > 600 filmes no total: test_db confere o corte padrão de 500 linhas pedindo 600.
MOVIES_WITH_REVENUE = 60
OTHER_MOVIES = 550


def build(source: Path = SOURCE, target: Path = TARGET) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)

    # uri=True para o ATTACH aceitar "?mode=ro": o banco real nunca é escrito.
    dst = sqlite3.connect(f"file:{target.as_posix()}", uri=True)
    dst.execute("ATTACH DATABASE ? AS src", (f"file:{source.as_posix()}?mode=ro",))

    ddl = dst.execute(
        "SELECT type, sql FROM src.sqlite_master WHERE sql IS NOT NULL "
        "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"
    ).fetchall()
    for _, sql in ddl:
        dst.execute(sql)

    dst.executescript(
        f"""
        CREATE TEMP TABLE sample_movies AS
          SELECT sk_movie_id FROM (
            SELECT f.sk_movie_id FROM src.fact_movies_performance f
            WHERE f.receita_usd IS NOT NULL AND f.orcamento_usd IS NOT NULL
            ORDER BY f.popularidade DESC LIMIT {MOVIES_WITH_REVENUE}
          )
          UNION
          SELECT sk_movie_id FROM (
            SELECT f.sk_movie_id FROM src.fact_movies_performance f
            WHERE f.receita_usd IS NULL AND f.popularidade IS NOT NULL
            ORDER BY f.popularidade ASC LIMIT {OTHER_MOVIES}
          );

        INSERT INTO main.alembic_version SELECT * FROM src.alembic_version;
        INSERT INTO main.dim_genres SELECT * FROM src.dim_genres;
        INSERT INTO main.dim_movies
          SELECT * FROM src.dim_movies WHERE sk_movie_id IN (SELECT sk_movie_id FROM sample_movies);
        INSERT INTO main.fact_movies_performance
          SELECT * FROM src.fact_movies_performance WHERE sk_movie_id IN (SELECT sk_movie_id FROM sample_movies);
        INSERT INTO main.bridge_movie_genre
          SELECT * FROM src.bridge_movie_genre WHERE sk_movie_id IN (SELECT sk_movie_id FROM sample_movies);
        INSERT INTO main.bridge_movie_person
          SELECT * FROM src.bridge_movie_person WHERE sk_movie_id IN (SELECT sk_movie_id FROM sample_movies);
        INSERT INTO main.dim_people
          SELECT * FROM src.dim_people
          WHERE sk_person_id IN (SELECT sk_person_id FROM main.bridge_movie_person);
        INSERT INTO main.bridge_movie_company
          SELECT * FROM src.bridge_movie_company WHERE sk_movie_id IN (SELECT sk_movie_id FROM sample_movies);
        INSERT INTO main.dim_companies
          SELECT * FROM src.dim_companies
          WHERE sk_company_id IN (SELECT sk_company_id FROM main.bridge_movie_company);
        INSERT INTO main.dim_reviews
          SELECT * FROM src.dim_reviews WHERE sk_movie_id IN (SELECT sk_movie_id FROM sample_movies);
        INSERT INTO main.movie_reviews
          SELECT * FROM src.movie_reviews WHERE sk_movie_id IN (SELECT sk_movie_id FROM sample_movies);
        """
    )
    dst.commit()
    dst.execute("DETACH DATABASE src")
    dst.execute("VACUUM")
    dst.close()


if __name__ == "__main__":
    build()
    with sqlite3.connect(TARGET) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for table in tables:
            print(f"{table}: {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
    print(f"{TARGET.relative_to(BASE_DIR)}: {TARGET.stat().st_size / 1_048_576:.1f} MB")

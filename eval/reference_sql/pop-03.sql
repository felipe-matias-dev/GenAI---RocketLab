SELECT m.ano_lancamento AS key_ano, AVG(f.nota_imdb) AS metric_nota_media
FROM dim_movies m JOIN fact_movies_performance f USING (sk_movie_id)
WHERE m.ano_lancamento IS NOT NULL AND f.nota_imdb IS NOT NULL
  AND m.data_lancamento <= date('now')
GROUP BY m.ano_lancamento

SELECT COUNT(DISTINCT b.sk_movie_id) AS metric_filmes
FROM bridge_movie_genre b JOIN dim_genres g USING (sk_genre_id)
WHERE g.nome_genero = 'Science Fiction'

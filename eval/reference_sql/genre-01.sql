SELECT g.nome_genero AS key_genero, COUNT(DISTINCT b.sk_movie_id) AS metric_filmes
FROM dim_genres g JOIN bridge_movie_genre b USING (sk_genre_id)
GROUP BY g.sk_genre_id

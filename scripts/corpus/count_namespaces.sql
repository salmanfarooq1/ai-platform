SELECT namespace, COUNT(*) as chunks FROM documents GROUP BY namespace ORDER BY namespace;

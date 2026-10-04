"""Sistema de recomendacion de productos basado en KNeighborsClassifier."""

from pathlib import Path
from typing import Any, Sequence

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


class RecommendationSystem:
	"""Entrena un clasificador KNN y recomienda productos similares."""

	def __init__(
		self,
		csv_path: str | Path = "products.csv",
		target_column: str = "category",
		id_column: str = "product_id",
		feature_columns: Sequence[str] | None = None,
		n_neighbors: int = 5,
		test_size: float = 0.2,
		random_state: int = 42,
	) -> None:
		self.products = pd.read_csv(csv_path)
		self.target_column = target_column
		self.id_column = id_column
		self.n_neighbors = n_neighbors

		required_columns = {target_column, id_column}
		missing_columns = required_columns.difference(self.products.columns)
		if missing_columns:
			missing = ", ".join(sorted(missing_columns))
			raise ValueError(f"Faltan columnas requeridas en el CSV: {missing}")
		if n_neighbors < 1:
			raise ValueError("n_neighbors debe ser al menos 1")
		if len(self.products) < 2:
			raise ValueError("Se necesitan al menos dos productos para entrenar")

		if feature_columns is None:
			excluded = {
				target_column,
				id_column,
				"name",
				"product_name",
				"title",
				"description",
				"product_description",
				"sku",
			}
			self.feature_columns = [
				column for column in self.products.columns if column not in excluded
			]
		else:
			self.feature_columns = list(feature_columns)
			missing_features = set(self.feature_columns).difference(self.products.columns)
			if missing_features:
				missing = ", ".join(sorted(missing_features))
				raise ValueError(f"No existen estas columnas de caracteristicas: {missing}")

		if not self.feature_columns:
			raise ValueError("No hay columnas de caracteristicas para entrenar")

		features = self.products[self.feature_columns]
		labels = self.products[target_column]
		self._all_features = features

		self._numeric_columns = features.select_dtypes(include="number").columns.tolist()
		self._categorical_columns = [
			column for column in self.feature_columns if column not in self._numeric_columns
		]
		transformers = []
		if self._numeric_columns:
			numeric_pipeline = Pipeline(
				steps=[
					("imputer", SimpleImputer(strategy="median")),
					("scaler", StandardScaler()),
				]
			)
			transformers.append(("numeric", numeric_pipeline, self._numeric_columns))
		if self._categorical_columns:
			categorical_pipeline = Pipeline(
				steps=[
					("imputer", SimpleImputer(strategy="most_frequent")),
					("onehot", OneHotEncoder(handle_unknown="ignore")),
				]
			)
			transformers.append(
				("categorical", categorical_pipeline, self._categorical_columns)
			)

		self.preprocessor = ColumnTransformer(transformers=transformers)
		train_indices, test_indices = train_test_split(
			self.products.index,
			test_size=test_size,
			random_state=random_state,
		)
		self.model = KNeighborsClassifier(
			n_neighbors=min(n_neighbors, len(train_indices))
		)
		self._train_products = self.products.loc[train_indices].reset_index(drop=True)
		self._train_labels = labels.loc[train_indices].reset_index(drop=True)
		test_features = features.loc[test_indices]
		test_labels = labels.loc[test_indices]

		train_matrix = self.preprocessor.fit_transform(
			self._train_products[self.feature_columns]
		)
		test_matrix = self.preprocessor.transform(test_features)
		self.model.fit(train_matrix, self._train_labels)
		predictions = self.model.predict(test_matrix)
		self.accuracy = accuracy_score(test_labels, predictions)

	def recommend(self, product_id: Any, n: int = 5) -> pd.DataFrame:
		"""Devuelve hasta n productos similares al producto identificado."""
		if n < 1:
			raise ValueError("n debe ser al menos 1")

		matches = self.products[self.products[self.id_column] == product_id]
		if matches.empty:
			raise KeyError(f"No se encontro el producto con id {product_id!r}")

		query = matches.iloc[[0]][self.feature_columns]
		query_matrix = self.preprocessor.transform(query)
		predicted_category = self.model.predict(query_matrix)[0]
		distances, neighbor_indices = self.model.kneighbors(
			query_matrix,
			n_neighbors=len(self._train_products),
		)

		recommendations = []
		for distance, index in zip(distances[0], neighbor_indices[0]):
			candidate = self._train_products.iloc[index]
			if candidate[self.id_column] == product_id:
				continue
			if self._train_labels.iloc[index] != predicted_category:
				continue
			recommendation = candidate.copy()
			recommendation["distance"] = float(distance)
			recommendations.append(recommendation)
			if len(recommendations) == n:
				break

		if not recommendations:
			return pd.DataFrame(columns=[*self.products.columns, "distance"])
		return pd.DataFrame(recommendations).reset_index(drop=True)


if __name__ == "__main__":
	recommender = RecommendationSystem("products.csv")
	print(f"Accuracy: {recommender.accuracy:.2%}")
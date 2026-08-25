"""Just enough linear algebra, in pure Python.  `jacobi_eigenvalue_clipping_v1`

The engine has no third-party numerical dependency and this module is why one
is not needed. Everything here operates on small symmetric matrices - one row
per curve tenor, so ten or eleven - where a hand-written Jacobi rotation is
both fast enough and easier to audit than a call into a binary wheel.

The important function is `nearest_psd`. A covariance matrix estimated from
overlapping h-day changes, or a correlation matrix a caller typed in by hand,
is routinely *not* positive semidefinite. Factorising it anyway yields complex
"volatilities" or silently negative variances, and the simulation that follows
looks completely normal. So the choice is made explicitly: repair the matrix
and say by how much, or refuse. Never proceed on an invalid one.
"""

from __future__ import annotations

import math

Matrix = list[list[float]]


class MatrixError(ValueError):
    """The matrix is not of a shape or kind this module can work with."""


def is_square_symmetric(m: Matrix, tolerance: float = 1e-9) -> bool:
    n = len(m)
    if n == 0 or any(len(row) != n for row in m):
        return False
    return all(abs(m[i][j] - m[j][i]) <= tolerance * max(1.0, abs(m[i][j]))
               for i in range(n) for j in range(i + 1, n))


def symmetrise(m: Matrix) -> Matrix:
    n = len(m)
    return [[(m[i][j] + m[j][i]) / 2.0 for j in range(n)] for i in range(n)]


def jacobi_eigen(m: Matrix, max_sweeps: int = 100,
                 tolerance: float = 1e-12) -> tuple[list[float], Matrix]:
    """Eigenvalues and eigenvectors of a real symmetric matrix.

    Cyclic Jacobi. Returns (eigenvalues, eigenvectors-as-columns). Chosen over a
    QR implementation because it is unconditionally stable on symmetric input
    and short enough to read in one sitting.
    """
    if not is_square_symmetric(m):
        raise MatrixError("eigen decomposition requires a square symmetric matrix")
    n = len(m)
    a = [row[:] for row in m]
    v: Matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

    for _ in range(max_sweeps):
        off = math.sqrt(sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j))
        if off <= tolerance:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) <= tolerance:
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
                t = math.copysign(1.0, theta) / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    return [a[i][i] for i in range(n)], v


def min_eigenvalue(m: Matrix) -> float:
    return min(jacobi_eigen(m)[0])


def is_positive_semidefinite(m: Matrix, tolerance: float = -1e-10) -> bool:
    return min_eigenvalue(m) >= tolerance


def nearest_psd(m: Matrix, floor: float = 0.0) -> tuple[Matrix, dict[str, float]]:
    """Clip negative eigenvalues to `floor` and rebuild.

    Higham's alternating-projection method is closer in the Frobenius sense;
    eigenvalue clipping is a single deterministic step whose distortion can be
    reported exactly, and reporting it is what stops a repaired matrix from
    being mistaken for the estimated one.
    """
    sym = symmetrise(m)
    values, vectors = jacobi_eigen(sym)
    smallest = min(values)
    clipped = [max(v, floor) for v in values]
    n = len(sym)
    out = [[sum(vectors[i][k] * clipped[k] * vectors[j][k] for k in range(n))
            for j in range(n)] for i in range(n)]
    out = symmetrise(out)
    drift = max(abs(out[i][j] - sym[i][j]) for i in range(n) for j in range(n))
    return out, {
        "smallest_eigenvalue_before": smallest,
        "smallest_eigenvalue_after": min(clipped),
        "max_absolute_adjustment": drift,
        "eigenvalues_clipped": float(sum(1 for v in values if v < floor)),
    }


def cholesky(m: Matrix, jitter: float = 0.0) -> Matrix:
    """Lower-triangular L with L Lt = M. Raises if M is not positive definite."""
    n = len(m)
    lower: Matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                d = m[i][i] + jitter - total
                if d <= 0.0:
                    raise MatrixError(
                        f"matrix is not positive definite: pivot {d:.3e} at index {i}")
                lower[i][j] = math.sqrt(d)
            else:
                lower[i][j] = (m[i][j] - total) / lower[j][j]
    return lower


def psd_factor(m: Matrix) -> tuple[Matrix, dict[str, float]]:
    """A factor L with L Lt ~= M, repairing M first if it is not PSD.

    A degenerate matrix - a tenor with zero variance, or two tenors that moved
    identically over the window - is singular rather than indefinite, and a
    plain Cholesky refuses it. The eigenvalue route factors it anyway, which is
    correct: a zero-variance factor should simply never be shocked.
    """
    try:
        return cholesky(m), {"repaired": 0.0}
    except MatrixError:
        pass
    repaired, info = nearest_psd(m, floor=0.0)
    values, vectors = jacobi_eigen(repaired)
    n = len(repaired)
    root = [[vectors[i][k] * math.sqrt(max(values[k], 0.0)) for k in range(n)]
            for i in range(n)]
    return root, {"repaired": 1.0, **info}


def correlation_from_covariance(cov: Matrix) -> Matrix:
    n = len(cov)
    sd = [math.sqrt(cov[i][i]) if cov[i][i] > 0 else 0.0 for i in range(n)]
    return [[(cov[i][j] / (sd[i] * sd[j]) if sd[i] > 0 and sd[j] > 0
              else (1.0 if i == j else 0.0)) for j in range(n)] for i in range(n)]


def covariance_from_correlation(corr: Matrix, stdevs: list[float]) -> Matrix:
    n = len(corr)
    if len(stdevs) != n:
        raise MatrixError("correlation matrix and standard deviations differ in size")
    return [[corr[i][j] * stdevs[i] * stdevs[j] for j in range(n)] for i in range(n)]


def quadratic_form(vector: list[float], m: Matrix) -> float:
    """v' M v, the portfolio variance of an exposure vector."""
    n = len(vector)
    if len(m) != n:
        raise MatrixError("exposure vector and matrix differ in size")
    return sum(vector[i] * m[i][j] * vector[j] for i in range(n) for j in range(n))


def matrix_vector(m: Matrix, vector: list[float]) -> list[float]:
    return [sum(row[j] * vector[j] for j in range(len(vector))) for row in m]

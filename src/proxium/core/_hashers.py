import base64
import hashlib
import math
import secrets


class PBKDF2Hasher:
    algorithm: str = "pbkdf2_sha256"
    iterations: int = 600_000
    salt_entropy: int = 128
    separator: str = "."
    salt_chars: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def salt(self) -> str:
        length = math.ceil(self.salt_entropy / math.log2(len(self.salt_chars)))
        return "".join(secrets.choice(self.salt_chars) for _ in range(length))

    def encode(
        self,
        password: str,
        /,
        *,
        salt: str | None = None,
        iterations: int | None = None,
    ) -> str:
        salt = self.salt() if salt is None else salt
        iterations = self.iterations if iterations is None else iterations
        if not password:
            raise ValueError("Password must not be empty.")
        if not salt or self.separator in salt:
            raise ValueError(f"Salt must not be empty or contain {self.separator!r}.")

        hash_ = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            iterations,
        )
        hash_b64 = base64.b64encode(hash_).decode("ascii")
        return self.separator.join(
            (
                self.algorithm,
                str(iterations),
                salt,
                hash_b64,
            ),
        )

    def verify(
        self,
        password: str,
        encoded: str,
        /,
    ) -> bool:
        try:
            algorithm, iterations, salt, _ = encoded.split(self.separator, 3)
        except ValueError:
            return False
        if algorithm != self.algorithm or not password:
            return False
        expected = self.encode(
            password,
            salt=salt,
            iterations=int(iterations),
        )
        return secrets.compare_digest(
            encoded.encode(),
            expected.encode(),
        )


hasher = PBKDF2Hasher()

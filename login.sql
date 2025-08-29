USE finance_project;

CREATE TABLE IF NOT EXISTS user_info (
    id INT PRIMARY KEY AUTO_INCREMENT,
    login_name VARCHAR(55) UNIQUE NOT NULL,
    password_salt CHAR(36) NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    create_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    login_name VARCHAR(55),
    item_text VARCHAR(255),
    FOREIGN KEY (login_name) REFERENCES user_info(login_name)
        ON DELETE CASCADE
        ON UPDATE CASCADE
)

-- If you want to start at 1005987 and increment by 37:
ALTER TABLE user_info AUTO_INCREMENT = 1005987;

--
DROP FUNCTION IF EXISTS sfn_hash_password;
DELIMITER $$

CREATE FUNCTION sfn_hash_password(
    in_password VARCHAR(128),
    in_salt CHAR(36)
)
RETURNS VARCHAR(128)
DETERMINISTIC
BEGIN
    DECLARE pwd_and_salt VARCHAR(164);
    DECLARE hashed_password VARCHAR(128);

    -- Concatenate password and salt
    SET pwd_and_salt = CONCAT(in_password, in_salt);

    -- SHA2 returns hex string, 512 bits = 128 hex chars
    SET hashed_password = SHA2(pwd_and_salt, 512);

    RETURN hashed_password;
END$$

DELIMITER ;

--
DROP PROCEDURE IF EXISTS proc_register_user;
DELIMITER $$

CREATE PROCEDURE proc_register_user(
    IN in_login_name VARCHAR(50),
    IN in_password   VARCHAR(128)
)
BEGIN
    DECLARE v_salt CHAR(36);
    DECLARE v_hash VARCHAR(128);

    -- generate a new UUID salt
    SET v_salt = UUID();

    -- compute the hash using the stored function
    SET v_hash = sfn_hash_password(in_password, v_salt);

    -- insert the new user (will error if login_name UNIQUE constraint is violated)
    INSERT INTO user_info (login_name, password_salt, password_hash)
    VALUES (in_login_name, v_salt, v_hash);
END$$

DELIMITER ;

--
-- Remove old version if it exists
DROP FUNCTION IF EXISTS sfn_validate_user;

DELIMITER $$

CREATE FUNCTION sfn_validate_user(
    p_login_name     VARCHAR(50),
    p_input_password VARCHAR(128)
)
RETURNS BIT
DETERMINISTIC
BEGIN
    DECLARE v_stored_hash   VARCHAR(128);
    DECLARE v_password_salt CHAR(36);
    DECLARE v_is_valid      BIT DEFAULT 0;

    -- Step 1: Get stored hash and salt for the user
    SELECT password_hash, password_salt
    INTO v_stored_hash, v_password_salt
    FROM user_info
    WHERE login_name = p_login_name
    LIMIT 1;

    -- Step 2: Compare stored hash to hash of input password + salt
    IF v_stored_hash IS NOT NULL THEN
        IF v_stored_hash = sfn_hash_password(p_input_password, v_password_salt) THEN
            SET v_is_valid = 1;
        END IF;
    END IF;

    -- Step 3: Return 1 (valid) or 0 (invalid)
    RETURN v_is_valid;
END$$

DELIMITER ;
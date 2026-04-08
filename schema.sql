-- Run this once to set up the database
CREATE DATABASE IF NOT EXISTS stargazer_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE stargazer_db;

CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  UNIQUE NOT NULL,
    email         VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS favorites (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    city_name  VARCHAR(100) NOT NULL,
    added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_city (user_id, city_name),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Optional: search history for analytics
CREATE TABLE IF NOT EXISTS search_history (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT,
    city_name   VARCHAR(100) NOT NULL,
    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);
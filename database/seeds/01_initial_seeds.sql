-- =============================================================================
-- EXAMIND Seed Data: Initial Development & Demo Fixtures
-- Target: MySQL 8.0+ (served via XAMPP on default port 3306)
-- Encoding: UTF-8 Unicode (utf8mb4_unicode_ci)
-- =============================================================================

USE examind;

-- -----------------------------------------------------------------------------
-- 1. Insert Initial Users
-- Passwords below are hashed using bcrypt for "Password123!"
-- Hash: $2b$12$e8YkYxLw9J5kR7gL1b.2u.3qK4e0.wW2r7r7V0oE6a6Q5w0u1u4m2 (Dummy representation)
-- -----------------------------------------------------------------------------
INSERT INTO users (id, identifier, email, password_hash, full_name, role, is_active) VALUES
(1, 'admin', 'admin@examind.sch.id', '$2b$12$e8YkYxLw9J5kR7gL1b.2u.3qK4e0.wW2r7r7V0oE6a6Q5w0u1u4m2', 'Administrator Utama', 'admin', 1),
(2, '198507232010011005', 'guru.fisika@sekolah.sch.id', '$2b$12$e8YkYxLw9J5kR7gL1b.2u.3qK4e0.wW2r7r7V0oE6a6Q5w0u1u4m2', 'Budi Santoso, M.Pd.', 'teacher', 1),
(3, '0061234501', 'ahmad.dahlan@siswa.sch.id', '$2b$12$e8YkYxLw9J5kR7gL1b.2u.3qK4e0.wW2r7r7V0oE6a6Q5w0u1u4m2', 'Ahmad Dahlan', 'student', 1),
(4, '0061234502', 'citra.lestari@siswa.sch.id', '$2b$12$e8YkYxLw9J5kR7gL1b.2u.3qK4e0.wW2r7r7V0oE6a6Q5w0u1u4m2', 'Citra Lestari', 'student', 1),
(5, '0061234503', 'doni.pratama@siswa.sch.id', '$2b$12$e8YkYxLw9J5kR7gL1b.2u.3qK4e0.wW2r7r7V0oE6a6Q5w0u1u4m2', 'Doni Pratama', 'student', 1)
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name);

-- -----------------------------------------------------------------------------
-- 2. Insert Academic Class & Memberships
-- -----------------------------------------------------------------------------
INSERT INTO classes (id, name, grade_level, academic_year, created_by) VALUES
(1, 'XII MIPA 1', '12', '2026/2027', 1)
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO class_members (id, class_id, user_id, role) VALUES
(1, 1, 2, 'teacher'),
(2, 1, 3, 'student'),
(3, 1, 4, 'student'),
(4, 1, 5, 'student')
ON DUPLICATE KEY UPDATE role=VALUES(role);

-- -----------------------------------------------------------------------------
-- 3. Insert Question Bank & Sample Questions
-- -----------------------------------------------------------------------------
INSERT INTO question_banks (id, teacher_id, title, subject, description) VALUES
(1, 2, 'Bank Soal Fisika Kuantum & Gelombang', 'Fisika', 'Kumpulan soal persiapan Ujian Akhir Semester kelas XII')
ON DUPLICATE KEY UPDATE title=VALUES(title);

INSERT INTO questions (id, bank_id, question_type, prompt, options_json, correct_answer, rubric_json, explanation, difficulty, default_points) VALUES
(1, 1, 'multiple_choice', 
 'Pada peristiwa efek fotolistrik, energi kinetik maksimum elektron yang terlepas dari permukaan logam bergantung pada...',
 '[{"id":"A","text":"Intensitas cahaya yang menyinari"},{"id":"B","text":"Frekuensi cahaya yang menyinari"},{"id":"C","text":"Luas permukaan logam"},{"id":"D","text":"Lama penyinaran cahaya"}]',
 'B',
 NULL,
 'Berdasarkan teori foton Einstein, energi kinetik maksimum fotoelektron bergantung pada energi foton yang sebanding dengan frekuensinya (Ek = hf - W0), bukan intensitasnya.',
 'medium', 10.00),

(2, 1, 'multiple_choice', 
 'Sebuah foton memiliki panjang gelombang 660 nm. Jika konstanta Planck h = 6.6 x 10^-34 J.s dan kecepatan cahaya c = 3 x 10^8 m/s, maka energi foton tersebut adalah...',
 '[{"id":"A","text":"3.0 x 10^-19 Joule"},{"id":"B","text":"2.0 x 10^-19 Joule"},{"id":"C","text":"1.5 x 10^-19 Joule"},{"id":"D","text":"4.5 x 10^-19 Joule"}]',
 'A',
 NULL,
 'Energi foton dihitung dengan E = (h x c) / lambda = (6.6x10^-34 x 3x10^8) / (660x10^-9) = 3.0 x 10^-19 Joule.',
 'medium', 10.00),

(3, 1, 'long_essay', 
 'Jelaskan bagaimana teori kuantum Einstein berhasil menerangkan kelemahan teori gelombang klasik dalam menjelaskan efek fotolistrik!',
 NULL,
 'Efek fotolistrik tidak dapat dijelaskan dengan teori gelombang klasik karena teori klasik memprediksi adanya jeda waktu penyinaran dan ketergantungan energi kinetik pada intensitas. Einstein mengemukakan bahwa cahaya berupa paket kuantum diskrit (foton). Energi tiap foton bergantung pada frekuensinya. Elektron hanya terlepas jika energi foton melebihi fungsi kerja logam secara instan.',
 '{"dimension_1_concept":{"max":40,"criteria":"Menjelaskan konsep foton dan fungsi kerja"},"dimension_2_comparison":{"max":30,"criteria":"Membandingkan kelemahan teori gelombang klasik"},"dimension_3_terminology":{"max":15,"criteria":"Akurasi istilah fisika"},"dimension_4_clarity":{"max":15,"criteria":"Runtutan bahasa dan logika"}}',
 'Penjelasan yang tepat harus mencakup kegagalan teori gelombang klasik (prediksi jeda waktu dan intensitas) dan keberhasilan postulat kuantum Einstein (foton sebagai paket energi diskrit instan).',
 'hard', 20.00)
ON DUPLICATE KEY UPDATE prompt=VALUES(prompt);

-- -----------------------------------------------------------------------------
-- 4. Insert Demo Exam & Question Mappings
-- -----------------------------------------------------------------------------
INSERT INTO exams (id, teacher_id, class_id, title, description, duration_minutes, start_time, end_time, randomize_questions, randomize_options, proctoring_level, explanation_policy, status) VALUES
(1, 2, 1, 'Ujian Akhir Semester Fisika Kuantum', 'Ujian evaluasi materi Fisika Kuantum semester genap', 90, '2026-08-31 08:00:00', '2026-08-31 12:00:00', 1, 1, 'dual_camera', 'after_exam_closed', 'published')
ON DUPLICATE KEY UPDATE title=VALUES(title);

INSERT INTO exam_questions (id, exam_id, question_id, order_index, allocated_points) VALUES
(1, 1, 1, 1, 10.00),
(2, 1, 2, 2, 10.00),
(3, 1, 3, 3, 20.00)
ON DUPLICATE KEY UPDATE allocated_points=VALUES(allocated_points);

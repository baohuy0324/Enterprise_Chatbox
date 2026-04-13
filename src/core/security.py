import re

def is_safe_query(query: str) -> tuple[bool, str]:
    """
    Kiểm tra tính an toàn của truy vấn đầu vào nhằm chống prompt injection
    """
    if not query or not query.strip():
        return False, "Câu hỏi không được để trống."
        
    query_lower = query.lower()
    
    # 1. Chặn theo từ khóa mở rộng 
    blocked_keywords = [
        "ignore previous", 
        "ignore all",
        "system prompt", 
        "api key",
        "forget all",
        "bỏ qua các chỉ thị",
        "quên đi các lệnh",
        "hướng dẫn hệ thống",
        "you are now",
        "developer mode",
        "do anything now",
        "bypass",
        "tiết lộ prompt",
        "trở thành",
        "cư xử như",
        "act as",
        "jailbreak",
        "trả về luật",
        "các quy tắc ở trên",
        "print instructions",
        "hãy bỏ qua",
        "cung cấp cho tôi thông tin nội bộ",
        "đây là một quá trình kiểm thử",
    ]
    
    for word in blocked_keywords:
        if word in query_lower:
            return False, "Truy vấn chứa từ khoá can thiệp hệ thống bị cấm."
            
    # 2. Ngăn chặn các script SQL Injection hoặc Code Injection cơ bản bằng Regex
    suspicious_patterns = [
        r"(\b(select|update|delete|insert|drop|alter)\b.*\b(from|into|table)\b)", # Cú pháp SQL
        r"(<script.*?>.*?</script>)", # Chặn chèn mã HTML/JS (XSS)
        r"(eval\(|exec\()", # Hàm thực thi Python trực tiếp
        r"(base64)", # Cấm ép encode/decode mã độc
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, query_lower):
            return False, "Access Denied"
            
    # 3. Chặn câu hỏi quá dài 
    if len(query) > 1500:
        return False, "Access Denied: Độ dài câu hỏi vượt quá 1500 ký tự."

    return True, "Safe"

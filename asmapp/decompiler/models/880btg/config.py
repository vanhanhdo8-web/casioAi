# Cấu hình cho fx-880BTG (điều chỉnh từ bản dành cho fx-580VN X)
# Lưu ý: Kiểm tra lại địa chỉ vùng RAM thực tế của máy fx-880BTG
# (Có thể RAM lớn hơn, ví dụ 0xC000–0x10000 nếu dung lượng 16KB)

start_ram = 0x9000      # Địa chỉ bắt đầu vùng RAM (cần xác định lại cho 880)
end_ram   = 0xFFFF
      # Địa chỉ kết thúc vùng RAM (cần xác định lại)

disas_file   = 'disas.txt'     # File disassembly của 880 (cần tạo riêng)
gadgets_file = 'gadgets.txt'   # File gadgets của 880 (đã có)
labels_file  = 'labels.txt'    # File labels của 880 (nếu có)

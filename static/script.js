function confirmDelete() {
    return confirm("Are you sure you want to delete this service record?");
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".flash").forEach((message) => {
        setTimeout(() => {
            message.style.transition = "opacity 0.5s";
            message.style.opacity = "0";
            setTimeout(() => message.remove(), 500);
        }, 4000);
    });
});

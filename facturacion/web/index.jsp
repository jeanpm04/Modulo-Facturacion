<%@page import="SQL.connect" %>
<%@page contentType="text/html" pageEncoding="UTF-8"%>
<!DOCTYPE html>
<html>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
        <title>Conexión con SQL Workbench</title>
    </head>
    <body>
        <h1>Conexión</h1>
        <%
            try {
                connect con = new connect();
                out.write("Conexión exitosa");
            } catch (Exception e) {
                out.write("Ha ocurrido un error: " + e.getMessage());
            }
        %>
    </body>
</html>
